# gsmnode — Docker all-in-one

One container runs **PocketBase**, the **API Server** and the **Web App** (nginx
serving the SPA and proxying `/api/`) under supervisord. Use it when one host and
one thing to run is the point; to scale or upgrade the pieces independently, use
the three-container stack in [`../Docker`](../Docker).

```
Browser ─► nginx (:80) ──/api/*──► API Server (:8080) ─► PocketBase (:8070)
```

The build context is the project root, so the Dockerfiles can reach both
`API Server/` and `Web App/`. The image is not published anywhere — build it
here, or build, tag and push it to your own registry for the prod files.

## Files

| File | Use |
|---|---|
| `Dockerfile` | the all-in-one image |
| `Dockerfile.seaweedfs` | the same, plus SeaweedFS (`weed server -s3`) as a fourth process |
| `Dockerfile.seaweedfs.split` | the same, plus SeaweedFS's master, volume, filer, S3 gateway and admin UI as separate processes |
| `docker-compose.yml` / `.env.example` | builds `Dockerfile` from source |
| `docker-compose.prod.yml` / `.env.prod.example` | runs a prebuilt `AIO_IMAGE` |
| `docker-compose[.prod].{seaweedfs,seaweedfs.split,s3}.yml` | MMS attachments in S3 — see below |

Each compose file is configured from the `.env` example of the same name:

```sh
cp .env.example .env          # then edit — PB_ADMIN_* have no safe defaults
docker compose up -d --build
```

Then: web app on `http://host:8090/`, the API Server's panel on
`http://host:8080/`, PocketBase admin on `http://host:8070/_/`.

## Volumes

| Mount | Holds |
|---|---|
| `/pb/pb_data` | the PocketBase database, its backups, and — without S3 — MMS attachments |
| `/data` | the API Server's plugin config (`plugins.json`) and the settings the panel persists |
| `/seaweed/data` | MMS attachments, in the SeaweedFS images only |
| `/seaweed/admin` | the SeaweedFS admin UI's session key, in the split image only |

## File storage (SeaweedFS / S3)

MMS attachment bytes are PocketBase record files, which by default live in
`/pb/pb_data`. These files put them in an S3 bucket instead; clients never notice,
because attachments always travel through the API Server as base64. How it works,
what it does and does not migrate, and how to turn it back off are the same as in
the three-container stack — read
[`../Docker/README.md`](../Docker/README.md#file-storage-seaweedfs--s3) first.

| Shape | Prod (one container) | From source |
|---|---|---|
| **Local storage** — the default | `docker-compose.prod.yml` | `docker-compose.yml` |
| **SeaweedFS** | `docker-compose.prod.seaweedfs.yml` — `weed` baked into the image | `docker-compose.seaweedfs.yml` — SeaweedFS as containers beside it |
| **SeaweedFS, split into its roles** | `docker-compose.prod.seaweedfs.split.yml` — baked in, with the admin UI | `docker-compose.seaweedfs.split.yml` — six containers beside it |
| **An S3 endpoint outside it** | `docker-compose.prod.s3.yml` | `docker-compose.s3.yml` |

The two prod SeaweedFS files carry both `build:` and `image:`: `build` then `up`
on a host with the checkout, or set `AIO_IMAGE` to a registry tag, `push`, and
`pull` it elsewhere. Baking SeaweedFS in means a new SeaweedFS is a rebuild
(`SEAWEED_VERSION`), not a tag change; the from-source files keep it in its own
containers so it can be upgraded on its own.

Inside the baked images:

- `PB_S3_ACCESS_KEY` and `PB_S3_SECRET` are required — the gateway refuses to
  start without them rather than run open. In the split image they are seeded
  into the filer's IAM store as the identity `gsmnode`, next to any the admin UI
  adds.
- The split image's admin UI (`:23646`) needs `SEAWEED_ADMIN_PASSWORD` and is
  published on loopback by default; set `SEAWEED_ADMIN_BIND=0.0.0.0` behind a
  reverse proxy for a remote host.
- Only the S3 gateway (`8333`) and the admin UI bind beyond loopback. The volume
  server, on `8081` because `8080` is the API Server, serves file content by id
  with no authentication — never publish it.
- `/seaweed/data` uses the `weed server -dir` layout in every shape, so a
  `SEAWEED_DATA` volume moves between them with nothing to migrate.

Every SeaweedFS shape's healthcheck covers SeaweedFS as well as the three app
processes, so a wedged gateway shows up in `docker ps`.
