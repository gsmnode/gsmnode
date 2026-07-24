"""Checks on the built `gsmnode.plg`.

The plugin file is generated, committed, and then installed straight from a URL
by people who cannot see this repository. Nothing between here and their flash
drive re-reads `source/`, so the thing worth verifying is the artifact: that it
is well-formed, that its shell blocks parse, that it deletes only what it wrote
— and, the one that actually goes wrong, that it was rebuilt after the agent
definition last changed.
"""
from __future__ import annotations

import base64
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLG = ROOT / "gsmnode.plg"
SOURCE = ROOT / "source"

# The heredocs the install block unpacks, and the source file each one carries.
PAYLOADS = {"AGENT_DEFINITION": "gsmnode.xml", "AGENT_ICON": "gsmnode.png"}

# Everywhere the plugin is allowed to write, and so everywhere it may delete.
OWNED = (
    "/boot/config/plugins/gsmnode",
    "/boot/config/plugins/dynamix/notifications/agents/gsmnode.sh",
    "/boot/config/plugins/dynamix/notifications/agents-disabled/gsmnode.sh",
    "/usr/local/emhttp/plugins/dynamix/agents/gsmnode.xml",
    "/usr/local/emhttp/plugins/dynamix/icons/gsmnode.png",
)

BASH = shutil.which("bash")

TEXT = PLG.read_text(encoding="utf-8")
ENTITIES = dict(re.findall(r'<!ENTITY\s+(\S+)\s+"([^"]*)"', TEXT))


def _expanded() -> str:
    """The plugin with its own entities resolved, as PHP's parser would see it.

    The DOCTYPE's internal subset is what carries them, and some are built out
    of the others. ElementTree refuses the subset outright, so this does the
    expansion — which doubles as a check that every entity resolves.
    """
    text = TEXT
    for _ in range(len(ENTITIES) + 1):
        text = re.sub(r"&(\w+);", lambda m: ENTITIES.get(m.group(1), m.group(0)), text)
    assert not re.search(r"&(?!amp;|lt;|gt;|quot;|apos;|#)\w+;", text), "an entity did not resolve"
    return re.sub(r"<!DOCTYPE.*?\]>", "", text, flags=re.S)


PLUGIN = ET.fromstring(_expanded())
SHELL = [f.findtext("INLINE") or "" for f in PLUGIN.iter("FILE")]
INSTALL = next(block for block in SHELL if "base64 -d" in block)
REMOVE = [f.findtext("INLINE") or "" for f in PLUGIN.iter("FILE") if f.get("Method") == "remove"]


def heredoc(marker: str) -> bytes:
    match = re.search(rf"<<'{marker}'\n(.*?)\n{marker}\n", INSTALL, re.S)
    assert match, f"no {marker} heredoc in the plugin"
    return base64.b64decode(match.group(1))


class ManifestTests(unittest.TestCase):
    """What Unraid's plugin manager reads before it runs anything."""

    def test_the_plugin_is_well_formed_xml(self):
        self.assertEqual(PLUGIN.tag, "PLUGIN")

    def test_it_declares_where_it_installs_and_updates_from(self):
        self.assertEqual(PLUGIN.get("name"), "gsmnode")
        # Unraid refuses to install below `min`. 6.10 is the release that first
        # had the Notification Agents page this plugin adds a row to.
        self.assertEqual(PLUGIN.get("min"), "6.10.0")
        # Where "Update" looks, and where the plugin's link goes.
        self.assertTrue(PLUGIN.get("pluginURL").endswith("/gsmnode.plg"))
        self.assertEqual(PLUGIN.get("launch"), "Settings/Notifications")

    def test_the_version_is_the_date_format_unraid_sorts_by(self):
        self.assertRegex(ENTITIES["version"], r"^\d{4}\.\d{2}\.\d{2}$")

    def test_the_changelog_names_this_version(self):
        # The Plugins tab shows CHANGES; a version missing from it reads as an
        # update that did nothing.
        self.assertIn(f"###{ENTITIES['version']}", PLUGIN.findtext("CHANGES") or "")

    def test_the_file_has_no_carriage_returns(self):
        # It is built on Windows and run by bash on Unraid.
        self.assertNotIn(b"\r", PLG.read_bytes())


class PayloadTests(unittest.TestCase):
    """That the artifact carries what `source/` currently says."""

    def test_the_payload_matches_the_source_it_was_built_from(self):
        # The check that earns its keep: editing source/gsmnode.xml and
        # forgetting to run scripts/build-plg.sh ships the old agent to
        # everyone, with nothing to show for it in the diff.
        for marker, filename in PAYLOADS.items():
            with self.subTest(filename):
                on_disk = (SOURCE / filename).read_bytes()
                if filename.endswith(".xml"):
                    # The build normalises text; the icon rides byte for byte.
                    on_disk = on_disk.replace(b"\r\n", b"\n")
                self.assertEqual(
                    heredoc(marker), on_disk, f"gsmnode.plg is stale — rebuild it from {filename}"
                )

    def test_the_agent_it_carries_is_the_one_the_other_tests_check(self):
        self.assertEqual(ET.fromstring(heredoc("AGENT_DEFINITION")).findtext("Name"), "gsmnode")

    def test_the_icon_it_carries_is_a_png(self):
        # The page points an <img> at it; anything else is a broken image.
        self.assertTrue(heredoc("AGENT_ICON").startswith(b"\x89PNG\r\n"))


class InstallTests(unittest.TestCase):
    """What the install and remove blocks touch."""

    def test_it_installs_where_the_webgui_looks(self):
        # The page globs /usr/local/emhttp/plugins/dynamix/agents/*.xml for the
        # row, and takes its icon from /plugins/dynamix/icons/<name>.png.
        self.assertIn("/usr/local/emhttp/plugins/dynamix/agents/gsmnode.xml", INSTALL)
        self.assertIn("/usr/local/emhttp/plugins/dynamix/icons/gsmnode.png", INSTALL)
        # Both of those are on a RAM disk, so the flash drive keeps the
        # originals for the reinstall Unraid runs at boot to put them back.
        self.assertIn("/boot/config/plugins/gsmnode/gsmnode.xml", INSTALL)
        self.assertIn("/boot/config/plugins/gsmnode/gsmnode.png", INSTALL)

    def test_removing_the_plugin_takes_the_configured_agent_with_it(self):
        self.assertTrue(REMOVE, "the plugin has no remove block")
        body = "\n".join(REMOVE)
        # The saved agent is a standalone script holding the gsmnode password.
        # Left behind, it keeps texting from an account nothing on the server
        # explains any more.
        self.assertIn("rm -f /boot/config/plugins/dynamix/notifications/agents/gsmnode.sh", body)
        self.assertIn(
            "rm -f /boot/config/plugins/dynamix/notifications/agents-disabled/gsmnode.sh", body
        )

    def test_it_deletes_nothing_it_did_not_put_there(self):
        for target in re.findall(r"rm -[rf]+ (\S+)", "\n".join(REMOVE)):
            with self.subTest(target):
                self.assertTrue(
                    target.startswith(OWNED) or target == "/boot/config/plugins/gsmnode.plg",
                    target,
                )

    def test_the_paths_are_spelled_out_rather_than_built_from_variables(self):
        # Anyone can read this file before installing it, and a plugin that runs
        # rm -f should show what it deletes without the reader tracing a shell
        # variable to find out.
        for line in "\n".join(REMOVE).splitlines():
            if line.startswith("rm "):
                self.assertNotIn("$", line, line)

    @unittest.skipUnless(BASH, "needs bash to check the syntax")
    def test_every_shell_block_parses(self):
        # Pre-install, install, the message after it, and remove all run as
        # bash. A syntax error in any of them is a half-installed plugin.
        self.assertEqual(len(SHELL), 4, "expected pre-install, install, post-install and remove")
        for index, script in enumerate(SHELL):
            with self.subTest(block=index):
                result = subprocess.run(
                    [BASH, "-n"], input=script, capture_output=True, text=True
                )
                self.assertEqual(result.returncode, 0, result.stderr)


class BuildTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("sh"), "needs a POSIX shell")
    def test_building_again_reproduces_the_committed_file(self):
        # Builds into a temporary file rather than over the committed one, so a
        # stale gsmnode.plg fails here instead of being quietly repaired.
        with tempfile.TemporaryDirectory() as tmp:
            rebuilt = Path(tmp) / "gsmnode.plg"
            subprocess.run(
                [shutil.which("sh"), str(ROOT / "scripts" / "build-plg.sh"), str(rebuilt)],
                check=True,
                capture_output=True,
            )
            self.assertEqual(
                rebuilt.read_bytes(),
                PLG.read_bytes(),
                "gsmnode.plg differs from a fresh build — run scripts/build-plg.sh",
            )


if __name__ == "__main__":
    unittest.main()
