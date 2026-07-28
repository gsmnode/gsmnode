# gsmnode — Unraid Docker template

Runs the **all-in-one** gsmnode image (PocketBase + API Server + Web App) as a
single Unraid container. This is the Docker *container* template — for the
notification-agent plugin that sends Unraid alerts as SMS, see
[`../Unraid Plugin/`](../Unraid%20Plugin/).

## Heads up: the image is not published

Unlike the three images behind [`../Docker/`](../Docker/), the all-in-one image
is **not** on any registry. Build it from the project root and push it to a
registry you control:

```bash
docker build -f Docker-AIO/Dockerfile -t <registry>/gsmnode-aio:latest .
docker push <registry>/gsmnode-aio:latest
```

Then set the template's **Repository** field to that tag.

## Install

1. On Unraid, go to **Docker → Add Container**.
2. In **Template**, paste the raw URL of `gsmnode-aio.xml`, or drop the file in
   `/boot/config/plugins/dockerMan/templates-user/` to have it appear in the list.
3. Set **Repository** to your pushed image tag.
4. Fill in **PocketBase Admin Email/Password** (required) and, to get a Web App
   login on first boot, the **Super-Admin Email/Password**.
5. Apply.

Web App: `http://<server>:8090/` · PocketBase admin: `http://<server>:8070/_/` ·
API Server + panel: `http://<server>:8080/`

## Ports and paths

| Setting | Container | Default |
| --- | --- | --- |
| Web UI | `80` | host `8090` |
| PocketBase | `8070` | host `8070` |
| API Server | `8080` | host `8080` |
| Database | `/pb/pb_data` | `/mnt/user/appdata/gsmnode/pb_data` |
| App data | `/data` | `/mnt/user/appdata/gsmnode/data` |

Keep both appdata paths on persistent storage. `/data` holds plugin config with
credentials (e.g. IMAP/SMTP logins), so back it up alongside the database.

The container variables mirror
[`../Docker-AIO/.env.prod.example`](../Docker-AIO/.env.prod.example) — see it for
the full explanation of each setting.
