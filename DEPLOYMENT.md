# VPS deployment

The container runs the FastAPI service, simulator match workers, static web interface, SQLite catalog, and replay store. Persistent data lives in the `catan-data` Docker volume.

```bash
docker build -f Dockerfile.player -t catan-player:local .
docker compose up -d --build
docker compose ps
curl http://127.0.0.1/health
```

The Compose service binds FastAPI to `127.0.0.1:8000`; Caddy terminates public HTTPS. `CATAN_FRONTEND_ORIGINS` must contain the Vercel origin. `CATAN_AUTH_REQUIRED` defaults to `1` in Docker and must remain enabled in production so bot uploads and lobby mutations require a signed-in account.

Room batches default to at most 10 matches (`CATAN_MAX_BATCH_SIZE=10` in the Compose environment; configurable from 1–100). Keep the default initially on the VPS. The shared queue runs at most two isolated matches at once and shares capacity between rooms; increasing the batch limit does not increase concurrency. Run one API process so this limit and room locks remain shared. After a restart, unfinished jobs are marked failed, saved recordings remain available, and rooms can run again.

Accounts, PBKDF2 password hashes, hashed login sessions, bot ownership, rooms, and the match catalog live in `/data/catan.db`. Replay files live in `/data/replays`. Both are covered by the persistent `catan-data` volume; back it up before server migrations.

Uploaded players run in disposable containers, one per player instance, during validation and matches. The `runner` service controls those containers through Docker; only this trusted broker has the Docker socket. The API shares a private Unix socket with the broker and has no Docker socket. Player containers have neither socket, no mounted application data, no external networking, a read-only root filesystem, a private 16 MB temporary filesystem, an unprivileged user, dropped capabilities, and bounded CPU/memory/processes. The player image contains Python and the SDK, not the simulator or backend. No credentials are passed to it. Extra Python packages are not installed for uploads; local CLI development can still use the author's own environment.

The broker tests blocked application-file access, root filesystem writes and outbound networking before opening its socket. If this fails, or the broker is unavailable, hosted execution fails closed. Production requires `CATAN_PLAYER_MODE=runner`; there is no automatic local fallback. `CATAN_PLAYER_MODE=local` is for trusted local development with `CATAN_AUTH_REQUIRED=0`, not public hosting.

The default broker uses the host's Docker daemon, so it is a privileged trusted component despite dropping Linux capabilities in its own container. Keep the Docker socket inaccessible to users and other applications. A rootless Docker daemon can be selected with `CATAN_DOCKER_SOCKET=/run/user/<uid>/docker.sock` and `CATAN_DOCKER_GID` set to that socket's numeric group ID; build the player image in that daemon too. This deployment does not install or configure rootless Docker automatically. Containers share the host kernel: keep Docker/the host patched; a separate runner VM provides an additional boundary against container escapes.

Build the player image before each deployment, then rebuild/restart Compose. On startup the broker removes player containers left by its previous process; it also expires abandoned sessions. Run only one broker per `CATAN_RUNNER_ID` on a Docker daemon. Separate deployments must use different IDs (Compose uses `catan-production`).

Uploads run in a separate bounded validation queue (one validation at a time, up to eight waiting/active, one per account). Each checks loading/lifecycle, 12 decision scenarios and three full simulations. Validation reports persist in `player_validations` in the catalog database, are private to the uploader, and are separate from game history. Failed drafts do not create saved player versions; the name/version can be retried. Restarted validations fail with a retry message. Existing versions remain usable; their runtime is isolated even if they predate these checks.

Useful operations:

```bash
docker compose logs -f catan
docker compose restart catan
docker compose down
```

`docker compose down` preserves the named data volume. Do not add `--volumes` unless you intend to delete the database and every replay.
