# gsmnode — Unraid Plugin

Sends **Unraid notifications as SMS**, through the gsmnode **API Server** and an
Android phone on your gateway.

```
Unraid notification ──► agent ──► API Server (/api/messages) ──► your phone ──► SMS
```

Like every other client it talks **only** to the API Server, never to
PocketBase. Unlike the [Home Assistant Plugin](../Home%20Assistant%20Plugin/README.md),
this one only sends: Unraid has notifications to hand out, not events to receive.

It is a **notification agent** — the same kind of thing Unraid ships for
Telegram, Discord, Pushover and ntfy. So it appears where those do, is
configured the way those are, and is picked per severity the way those are. If
you have set one up before, there is nothing new here.

## Install

Needs Unraid **6.10** or newer — that is the release with the Notification
Agents page. The plugin refuses to install on anything older.

**Plugins → Install Plugin**, paste this, and **Install**:

```
https://raw.githubusercontent.com/freefall-dev/gsmnode-unraid/main/gsmnode.plg
```

It is one self-contained file: nothing is downloaded afterwards, and no package
is fetched from anywhere. You can read the whole thing before installing it.

## Set it up

Two steps, both in the webGUI, and neither is done for you — an agent that
installed itself already switched on and already texting would be worse.

### 1. Fill in the agent

**Settings → Notifications → Notification Agents → gsmnode**

| Field | What goes in it |
|---|---|
| **API Server URL** | Where the API Server answers, from this server. `http://192.168.1.10:8080`. A missing `http://` is filled in |
| **Account email** / **Account password** | A gsmnode account to send as. Make one in the Web App, or with the API Server's `create-user.mjs` |
| **Recipient numbers** | Who gets texted. Several, separated by commas. International format (`+441234567890`) always works |
| **Sending phone** | The gateway device id of the phone to send from — it is on the phone's card in the Web App's **Devices** tab. Leave it `auto` and the API Server picks whichever phone is online |
| **SIM slot** | `0` is the phone's SIM 1, `1` is SIM 2. Leave it `auto` for the phone's own default |
| **Maximum characters** | `320` — two SMS segments. Longer notifications are cut and end in `...`. `0` never cuts |
| **Notification Title** | Fields for the first line. `Subject` by default |
| **Notification Message** | Fields for the rest. `Description` by default |

Set **Agent function** to **Enabled**, press **Apply**, then **Test** — a real
SMS arrives, and anything that went wrong is printed instead.

Your server's hostname always goes in front of the title, so a text still says
which machine it came from when you run more than one.

### 2. Choose what gets texted

**Settings → Notifications → Notification Settings**

Tick **Agents** on the severities you want. This is the part people forget: the
agent can be filled in, enabled and passing its own test, and still never fire,
because nothing has been routed to agents.

**Warnings** and **Alerts** are the ones worth texting. Ticking **Normal** puts
every routine notice on your phone bill.

## What it sends

One `POST /api/messages` of `type: "sms"`, after a `POST /api/auth/login` for a
bearer token. No token is cached and nothing is written at send time, so a
notification leaves nothing behind on the flash drive.

The text is your server's hostname, then the fields you picked:

```
tower: Alert [TOWER] - array turned good
warning
Array has 8 disks (0 disabled)
```

## Known rough edges

These come from Unraid's agent framework and apply to every agent it hosts, not
just this one:

- **The password is stored in clear text**, in the generated agent script on the
  flash drive — as it is for Telegram's bot token and everyone else's. Give the
  server its own gsmnode account rather than reusing yours.
- **Avoid `"`, `$`, `` ` `` and `#` in field values.** The webGUI writes each
  setting into the script as `NAME="value"` and reads it back by stripping
  quotes, so those characters do not survive the round trip. A `$` in a password
  is expanded as a shell variable and the login silently fails.
- **The agent keeps working if you disable the plugin**, because it is a
  standalone script the webGUI wrote. Uninstalling removes it — that is why the
  remove step deletes the configured agent and not just the plugin.

## Files it installs

| Path | What |
|---|---|
| `/boot/config/plugins/gsmnode/` | The agent definition and its icon, on the flash drive |
| `/usr/local/emhttp/plugins/dynamix/agents/gsmnode.xml` | What puts the row on the Notification Agents page |
| `/usr/local/emhttp/plugins/dynamix/icons/gsmnode.png` | The icon on that row |
| `/boot/config/plugins/dynamix/notifications/agents/gsmnode.sh` | Written by the webGUI when you press Apply — the agent itself |

The two under `/usr/local/emhttp` are on a RAM disk. Unraid reinstalls every
plugin at boot, which puts them back from the flash drive.

## Working on it

```sh
sh scripts/build-plg.sh      # rebuild gsmnode.plg from source/
python -m unittest discover tests
```

`source/gsmnode.xml` is the agent, and the only file worth editing. It is *not*
run as written: the Notification Agents page trims every line, drops the blank
ones, splices your settings in between the two hash rulers, and writes the
result out as the agent. The tests reproduce that and check what comes out —
including running it against a stand-in API Server, where `bash`, `curl` and
`jq` are all present.

`gsmnode.plg` is generated and committed, because that file *is* the release. A
test fails if it no longer matches `source/`.

Publishing it is [PUBLISHING.md](PUBLISHING.md).

## License

[Apache License 2.0](LICENSE) — see [NOTICE](NOTICE) for the marks, which are
not covered by that grant.
