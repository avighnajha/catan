# VPS deployment

The container runs the FastAPI service, simulator match workers, static web interface, SQLite catalog, and replay store. Persistent data lives in the `catan-data` Docker volume.

```bash
docker compose up -d --build
docker compose ps
curl http://127.0.0.1/health
```

The Compose service binds FastAPI to `127.0.0.1:8000`; Caddy terminates public HTTPS. `CATAN_FRONTEND_ORIGINS` must contain the Vercel origin. `CATAN_AUTH_REQUIRED` defaults to `1` in Docker and must remain enabled in production so bot uploads and lobby mutations require a signed-in account.

Accounts, PBKDF2 password hashes, hashed login sessions, bot ownership, rooms, and the match catalog live in `/data/catan.db`. Replay files live in `/data/replays`. Both are covered by the persistent `catan-data` volume; back it up before server migrations.

Uploaded Player implementations execute in child processes with time and resource limits, but they are executable Python and are not a security boundary against a hostile author. Deploy this service for trusted participants. Public untrusted submissions require a separate locked-down runner host or per-match sandbox with no access to the application data volume.

Useful operations:

```bash
docker compose logs -f catan
docker compose restart catan
docker compose down
```

`docker compose down` preserves the named data volume. Do not add `--volumes` unless you intend to delete the database and every replay.
