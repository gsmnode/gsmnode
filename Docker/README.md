# gsmnode — Docker (multi-container stack)

Three containers — **PocketBase**, **API Server**, **Web App** — on one compose
network. This is the deployment to use unless you specifically want everything
in a single image; for that see [`../Docker-AIO`](../Docker-AIO).

```
Browser ─► Web App BFF (:8090) ──/api/*──► API Server (:8080) ─► PocketBase (:8070)
```

Only the Web App port is meant to be public. The API Server and the PocketBase
admin UI are published for convenience and, in the prod files, bound to
`127.0.0.1` by default.

| File | Use |
|---|---|
| `docker-compose.yml` | **builds from source** in this repo — for development and local testing |
| `docker-compose.prod.yml` | **pulls prebuilt images** from the registry — for deployment |
| `.env.example` / `.env.prod.example` | copy to `.env` for the matching compose file |
| `docker-compose[.prod].{seaweedfs,seaweedfs.split,s3}.yml` | the same stacks with MMS attachments in S3 — see [File storage](#file-storage-seaweedfs--s3) |
| `pocketbase/` | the PocketBase image (official release binary on alpine) |

## Run it

```bash
cd Docker
cp .env.example .env        # then edit — PB_ADMIN_* have no safe defaults
docker compose up -d --build
```

Production, from the registry:

```bash
cp .env.prod.example .env   # then edit
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

Then: web app on `http://host:8090/`, the API Server's panel on
`http://host:8080/`, PocketBase admin on `http://host:8070/_/`.

## First boot

Both steps are idempotent, so restarts and upgrades are safe:

1. **PocketBase** upserts its superuser from `PB_ADMIN_EMAIL` / `PB_ADMIN_PASSWORD`.
   This is the only way to create the first superuser — the REST API cannot
   bootstrap it. The API Server then authenticates with the same credentials.
2. **The API Server** creates any missing collections and reconciles existing
   ones, then creates the first app `superadmin` from
   `GSMNODE_SUPERADMIN_EMAIL` / `_PASSWORD` if no such user exists.

## Volumes

| Volume | Holds |
|---|---|
| `pb_data` | the PocketBase SQLite database, its backups, and — on the plain compose files — MMS attachments |
| `api_data` | the API Server's plugin state: `plugins.json` plus the settings the panel persists |
| `seaweed_data` | MMS attachments, on the SeaweedFS files only |

Back up all of them. Plugin config holds credentials such as IMAP/SMTP logins,
so treat `api_data` as sensitively as the database. In the prod files each one
defaults to a Docker-managed named volume; set `PB_DATA` / `API_DATA` /
`SEAWEED_DATA` to an absolute host path for a bind mount instead. The API Server
runs unprivileged, so a host path for `API_DATA` must be chowned first — the
command is in `.env.prod.example`.

## File storage (SeaweedFS / S3)

MMS attachment bytes — outbound and inbound — are stored as PocketBase record
files, which by default live inside `pb_data` next to the database. Further
compose files put them in an S3 bucket instead, so the blobs and the database can
be sized, backed up and moved independently. Nothing else changes: clients have
always sent and received attachments as base64 through the API Server, never by
storage URL, so the Web App, Phone Agent, Phone App and Home Assistant plugin
cannot tell the difference.

Each shape is one self-contained compose file — nothing to layer, nothing to
remember — with an `.env` example of the same name:

| Shape | From the registry | From source |
|---|---|---|
| **Local storage** — the default, unchanged | `docker-compose.prod.yml` | `docker-compose.yml` |
| **SeaweedFS in this stack** | `docker-compose.prod.seaweedfs.yml` | `docker-compose.seaweedfs.yml` |
| **SeaweedFS, split into its roles** | `docker-compose.prod.seaweedfs.split.yml` | `docker-compose.seaweedfs.split.yml` |
| **An S3 endpoint outside it** | `docker-compose.prod.s3.yml` | `docker-compose.s3.yml` |

So `docker-compose.prod.seaweedfs.yml` is configured from
`.env.prod.seaweedfs.example`, `docker-compose.s3.yml` from `.env.s3.example`,
and so on:

```sh
cp .env.prod.seaweedfs.example .env    # then edit it — PB_S3_* have no defaults
docker compose -f docker-compose.prod.seaweedfs.yml pull
docker compose -f docker-compose.prod.seaweedfs.yml up -d
```

Set `PB_S3_ACCESS_KEY` and `PB_S3_SECRET` first — every storage file refuses to
start without them. The SeaweedFS ones add a `seaweedfs` container (master,
volume, filer and S3 gateway in one process, on its own `seaweed_data` volume)
plus a one-shot `seaweedfs-init` that creates the bucket, because PocketBase never
issues a `CreateBucket` of its own. The external-S3 ones add no containers at
all: set `PB_S3_ENDPOINT`, and create the bucket yourself.

### Split SeaweedFS

`weed server -s3` runs master, volume, filer and gateway as four goroutines in
one process. The `.split.` files run them as four containers, plus a fifth: the
SeaweedFS **admin UI** on port 23646, where the cluster can be inspected and —
under *Object Store → Users* — further S3 identities minted and revoked. Split
also gets you per-role restarts and upgrades, per-role Prometheus metrics, and
room to add a second volume server later.

Identities work differently there, and it matters. SeaweedFS reads credentials
from, in descending priority: an `-s3.config` file, the filer's IAM store, then
`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` — and a higher source *replaces*
a lower one rather than adding to it. The single-process files use the env vars,
which is why nothing else may write identities there: the first user added in a
panel would displace PocketBase's key. So in the split files `seaweedfs-init`
seeds PocketBase's identity into the filer's store instead — the same store the
admin UI writes — and the gateway runs with no config file at all. One source of
truth, PocketBase's key visible in the panel beside every other, and new keys
picked up without a restart. Rotating `PB_S3_SECRET` in `.env` and restarting
updates that identity in place.

Set `SEAWEED_ADMIN_PASSWORD`: `weed admin` serves the panel with no
authentication when it is empty, and a panel that can mint bucket credentials is
the bucket. In the prod file it is bound to loopback like `PB_BIND` and
`API_BIND`, so a remote host needs `SEAWEED_ADMIN_BIND=0.0.0.0` behind the same
reverse proxy. That file publishes nothing for master, volume and filer — the
volume server serves file content by id with no authentication of any kind, and
the admin UI already shows what those ports would.

Switching between `docker-compose.seaweedfs.yml` and its `.split.` twin needs no
migration: master, volume and filer share one `/data` mount, which is exactly
the layout `weed server -dir=/data` writes.

### What the API Server does

On every boot the API Server's bootstrap writes PocketBase's *Files storage*
settings from the `PB_S3_*` variables, then asks PocketBase to prove it can reach
the bucket. Watch for it in the log:

```
[api] bootstrap: ✓ file storage → S3 (gsmnode at http://seaweedfs:8333)
[api] bootstrap: ✓ S3 storage reachable
```

A boot that finds the settings already correct logs `• file storage already on S3`
and writes nothing.

Each MMS record keeps its attachment bytes in a `files` field and only the
metadata — filename, content type, and which file is which — in its
`attachments` JSON. When a phone pulls an outbound MMS, the API Server reads the
bytes back from storage before handing the message over; if storage is
unreachable the message stays `Pending` for the next pull rather than going out
with parts missing.

Two things to know before turning it on:

- **Existing files are not migrated.** PocketBase copies nothing when the setting
  flips, so attachments stored before the switch stop resolving. Copy
  `pb_data/storage/<collectionId>/<recordId>/<file>` into the bucket root, keeping
  that layout, *before* enabling it — or start from a stack with no MMS history.
  MMS records written before attachments moved to file storage at all keep their
  base64 inline in the record, and are unaffected either way.
- **Going back to the plain compose file is not an off switch.** It leaves
  PocketBase pointed at the bucket, deliberately: files already written there are
  reachable only while it is. Move them back and turn it off in PocketBase's own
  admin UI. For the same reason a rotation of `PB_S3_SECRET` alone is invisible
  to the bootstrap — PocketBase masks the stored secret on read — so change
  another `PB_S3_*` value alongside it, or set it in the admin UI.

## Notes

- `docker-compose.yml` builds the API Server and Web App from `../API Server`
  and `../Web App`, so run it from this directory with the repo checked out.
- The Web App's Vue bundle is built with an empty `VITE_API_BASE`, so the
  browser uses same-origin `/api` and the BFF proxies it — no CORS in play.
- `CORS_ALLOW_ORIGINS` therefore only matters if a browser calls the API Server
  directly. Native mobile apps are not subject to CORS at all.
