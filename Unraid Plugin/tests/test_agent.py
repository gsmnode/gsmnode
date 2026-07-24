"""Checks on the agent definition that Unraid's webGUI would only find at runtime.

`source/gsmnode.xml` is not run as written. Unraid's Notification Agents page
takes the `<Script>` template apart line by line, drops the blank ones, trims
every remaining one, substitutes the settings, and writes the result to the
flash drive as the agent. Anything the template relies on that does not survive
that — indentation, blank lines, a `{0}`-shaped placeholder, a run of hashes —
breaks the agent, and nothing says so until a notification is missed.

So these tests render the script the way the page does, then check the thing
that actually runs: first that it parses, then, where bash, curl and jq are all
present, that it really does log in and queue the text.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

AGENT_XML = Path(__file__).resolve().parent.parent / "source" / "gsmnode.xml"

# What the notify script exports, and what the page's title/message pickers
# offer. `notify` spells them in capitals; the picker labels them in title case.
NOTIFY_ENV = ["EVENT", "SUBJECT", "TIMESTAMP", "DESCRIPTION", "IMPORTANCE", "CONTENT", "LINK"]

# How the page reads a saved agent back to repopulate the form:
# preg_match("/[#]{6,100}([^#]*?)[#]{6,100}/si", ...) over the whole file.
VALUES_BLOCK = re.compile(r"[#]{6,100}([^#]*?)[#]{6,100}", re.S | re.I)

# What String.prototype.format substitutes into the template: {0} is the
# settings block and {1} a newline. Any other {digits} is eaten the same way.
PLACEHOLDER = re.compile(r"{(\d+)}")

AGENT = ET.parse(AGENT_XML).getroot()
TEMPLATE = AGENT.findtext("Script") or ""
DEFAULTS = {v.text or "": v.get("Default", "") for v in AGENT.find("Variables")}

BASH = shutil.which("bash")
CAN_RUN_THE_AGENT = all(map(shutil.which, ("bash", "jq", "curl")))


def render(values: dict[str, str], template: str = TEMPLATE) -> str:
    """Reproduce what the page writes to the flash drive.

    The PHP half joins the non-blank trimmed lines with `{1}`; the JavaScript
    half then formats `{0}` to the settings block and `{1}` to a newline.
    """
    joined = "".join(
        line.strip() + "{1}" for line in template.split("\n") if line.strip()
    )
    block = "\n".join(f'{name}="{value}"' for name, value in values.items())
    return PLACEHOLDER.sub(lambda m: [block, "\n"][int(m.group(1))], joined)


def check_syntax(script: str) -> subprocess.CompletedProcess:
    return subprocess.run([BASH, "-n"], input=script, capture_output=True, text=True)


class AgentDefinitionTests(unittest.TestCase):
    """The shape of the definition, and what the page makes of it."""

    def test_it_is_named_for_the_script_and_icon_the_plugin_installs(self):
        # The page derives both from <Name>: `<name>.sh` on the flash drive, and
        # /plugins/dynamix/icons/<name>.png for the row's icon.
        self.assertEqual(AGENT.findtext("Name"), "gsmnode")

    def test_the_settings_that_may_be_left_alone_have_a_default_that_says_so(self):
        # The page marks every non-picker input `required`, so a setting that
        # can be skipped needs a value meaning "skipped" — blank will not save.
        for name, expected in {"DEVICE_ID": "auto", "SIM_SLOT": "auto", "MAX_LENGTH": "320"}.items():
            self.assertEqual(DEFAULTS[name], expected, name)

    def test_the_pickers_are_the_two_the_page_recognises(self):
        # The page turns a variable into a multi-select of notification fields
        # when its Desc matches /title|message/ lowercased, and a text box if
        # not. The trap runs both ways: "Maximum message length" would silently
        # become a field picker instead of a number box.
        pickers = {
            v.text
            for v in AGENT.find("Variables")
            if re.search("title|message", v.get("Desc", "").lower())
        }
        self.assertEqual(pickers, {"TITLE", "MESSAGE"})

    def test_the_defaults_name_fields_the_notify_script_actually_exports(self):
        # A typo here sends an empty text, which still costs money.
        for name in re.findall(r"\$([A-Z_]+)", DEFAULTS["TITLE"] + DEFAULTS["MESSAGE"]):
            self.assertIn(name, NOTIFY_ENV)


class RenderingTests(unittest.TestCase):
    """What survives the page's line-by-line rewrite of the template."""

    def test_the_template_uses_only_the_placeholder_the_page_fills(self):
        # A `{2}` anywhere — a regex quantifier, say — is replaced with nothing.
        self.assertEqual(set(PLACEHOLDER.findall(TEMPLATE)), {"0"})

    def test_the_rendered_script_keeps_no_placeholders(self):
        self.assertIsNone(PLACEHOLDER.search(render(DEFAULTS)))

    def test_the_settings_survive_the_round_trip_back_into_the_form(self):
        # Reopening the page re-reads the saved script to fill the form in. If
        # the hash rulers do not sit either side of exactly the settings, the
        # form comes back empty and applying it wipes the configuration.
        values = dict(DEFAULTS, API_URL="http://192.0.2.10:8080", EMAIL="unraid@example.com")
        match = VALUES_BLOCK.search(render(values))
        self.assertIsNotNone(match)
        read_back = dict(
            line.replace('"', "").split("=", 1)
            for line in match.group(1).split("\n")
            if "=" in line
        )
        self.assertEqual(read_back, values)

    def test_the_script_body_carries_no_run_of_hashes(self):
        # The read-back regex is non-greedy, so the first six-hash run after the
        # settings closes the block. Keeping the body clean of them means the
        # rulers stay the only thing that can.
        body = render(DEFAULTS).split("############", 2)[-1]
        self.assertIsNone(re.search(r"[#]{6,}", body))

    @unittest.skipUnless(BASH, "needs bash to check the syntax")
    def test_the_rendered_script_is_valid_bash(self):
        # The whole point: what the page writes out has to parse. Losing the
        # indentation is what usually breaks this.
        result = check_syntax(render(DEFAULTS))
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(BASH, "needs bash to check the syntax")
    def test_a_password_with_a_quote_in_it_cannot_break_the_script(self):
        # The page's addSlashes() escapes quotes on the way in and its read-back
        # strips them on the way out, so a quote is mangled either way — but it
        # must not turn the settings block into something bash misparses.
        result = check_syntax(render(dict(DEFAULTS, PASSWORD='pa\\"ss')))
        self.assertEqual(result.returncode, 0, result.stderr)


class StubAPI(BaseHTTPRequestHandler):
    """Answers the two calls the agent makes, and records what it was sent."""

    calls: list[dict] = []

    def log_message(self, *args):  # keep the test output quiet
        pass

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's spelling
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.calls.append(
            {
                "path": self.path,
                "auth": self.headers.get("Authorization"),
                "body": json.loads(body or b"{}"),
            }
        )
        if self.path == "/api/auth/login":
            reply, status = {"access_token": "test-token"}, 200
        elif self.path == "/api/messages":
            reply, status = {"id": "rec1", "status": "Pending"}, 202
        else:
            reply, status = {"error": "no such endpoint"}, 404
        raw = json.dumps(reply).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


NOTIFICATION = {
    "TIMESTAMP": "1784000000",
    "EVENT": "Unraid Status",
    "SUBJECT": "Alert [TOWER] - array turned good",
    "DESCRIPTION": "Array has 8 disks (0 disabled)",
    "IMPORTANCE": "warning",
    "CONTENT": "disk1 is back online",
    "LINK": "http://tower/Dashboard",
}


@unittest.skipUnless(CAN_RUN_THE_AGENT, "needs bash, jq and curl — what the agent needs")
class RunningTheAgentTests(unittest.TestCase):
    """The agent against a stand-in API Server, as Unraid would run it."""

    def setUp(self):
        StubAPI.calls = []
        self.server = HTTPServer(("127.0.0.1", 0), StubAPI)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_agent(self, values, **notification):
        agent = Path(self.tmp.name) / "gsmnode.sh"
        agent.write_text(render(values), newline="\n", encoding="utf-8")
        return subprocess.run(
            [BASH, str(agent)],
            env={"PATH": os.environ["PATH"], **NOTIFICATION, **notification},
            capture_output=True,
            text=True,
        )

    def settings(self, **overrides):
        return DEFAULTS | {
            "API_URL": self.url,
            "EMAIL": "unraid@example.com",
            "PASSWORD": "correct-horse-battery",
            "PHONE_NUMBERS": "+441234567890",
        } | overrides

    def test_it_logs_in_and_queues_an_sms(self):
        result = self.run_agent(
            self.settings(
                # A trailing slash is the easiest thing to paste in by accident.
                API_URL=self.url + "/",
                PHONE_NUMBERS=" +441234567890 , +447777000111 ",
                SIM_SLOT="1",
                TITLE=r"$SUBJECT\n$IMPORTANCE",
            )
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        login, send = StubAPI.calls
        self.assertEqual(login["path"], "/api/auth/login")
        self.assertEqual(
            login["body"], {"email": "unraid@example.com", "password": "correct-horse-battery"}
        )

        self.assertEqual(send["path"], "/api/messages")
        self.assertEqual(send["auth"], "Bearer test-token")
        self.assertEqual(send["body"]["type"], "sms")
        # Split on the commas, trimmed, and sent as an array.
        self.assertEqual(send["body"]["phone_numbers"], ["+441234567890", "+447777000111"])
        self.assertEqual(send["body"]["sim_number"], 1)
        # Hostname, then the picked fields with the picker's \n made real.
        self.assertTrue(
            send["body"]["text_message"].endswith(
                f": {NOTIFICATION['SUBJECT']}\n{NOTIFICATION['IMPORTANCE']}"
                f"\n{NOTIFICATION['DESCRIPTION']}"
            ),
            send["body"]["text_message"],
        )
        # DEVICE_ID left at "auto" lets the API Server pick a phone that is up.
        self.assertNotIn("device_id", send["body"])

    def test_a_url_without_a_scheme_still_reaches_the_server(self):
        result = self.run_agent(self.settings(API_URL=self.url.removeprefix("http://")))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            [call["path"] for call in StubAPI.calls], ["/api/auth/login", "/api/messages"]
        )

    def test_a_long_notification_is_cut_to_the_configured_length(self):
        # Every segment over the limit is another SMS the user pays for, so this
        # is the setting that keeps a runaway notification from costing money.
        result = self.run_agent(self.settings(MAX_LENGTH="80"), DESCRIPTION="x" * 500)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = StubAPI.calls[1]["body"]["text_message"]
        self.assertEqual(len(text), 80)
        self.assertTrue(text.endswith("..."), text)

    def test_a_chosen_phone_is_named_on_the_wire(self):
        result = self.run_agent(self.settings(DEVICE_ID="pixel-7a", SIM_SLOT="auto"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        body = StubAPI.calls[1]["body"]
        self.assertEqual(body["device_id"], "pixel-7a")
        # "auto" is the page's stand-in for blank and must not reach the API
        # Server as a SIM slot — slot 0 is a real SIM, so a guess here texts
        # from the wrong one.
        self.assertNotIn("sim_number", body)

    def test_a_half_filled_agent_says_what_is_missing(self):
        # This output is all the user gets from the page's Test button.
        for broken, expected in [
            ({"API_URL": ""}, "no API Server URL configured"),
            ({"EMAIL": ""}, "no account email configured"),
            ({"PASSWORD": ""}, "no account password configured"),
            ({"PHONE_NUMBERS": " , "}, "no recipient numbers configured"),
        ]:
            with self.subTest(**broken):
                result = self.run_agent(self.settings(**broken))
                self.assertEqual(result.returncode, 1)
                self.assertIn(expected, result.stdout)

    def test_an_unreachable_server_is_reported_not_swallowed(self):
        result = self.run_agent(self.settings(API_URL="http://127.0.0.1:1"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("cannot reach http://127.0.0.1:1", result.stdout)

    def test_a_rejected_login_is_reported(self):
        # The stub only answers /api/auth/login; anything else 404s with an
        # error body, which is what a wrong password looks like from here.
        result = self.run_agent(self.settings(API_URL=self.url + "/wrong"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("login failed", result.stdout)


if __name__ == "__main__":
    unittest.main()
