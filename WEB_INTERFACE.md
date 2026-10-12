# Replay-first web interface

The platform now follows **room → simulate → saved recording → watch independently**. There is no live game WebSocket. Room and job pages poll for status; playback reads a completed recording and does not rerun bots.

## Run locally

```powershell
python -m pip install -r requirements.txt
python -m uvicorn src.platform.server:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Python runs the application; Node is needed only for browser development/tests. Serve one API process: it owns the shared match queue (do not use multiple Uvicorn workers).

Sign in or create an account, upload a Player version under **My bots**, create or join a room, and select a version. Once the final lineup is selected, all human participants mark ready; simulation opponents are automatically ready. Four ready seats allow the room creator to simulate one match or a batch. Recordings remain available under Matches and in the room history.

Docker enables authenticated API access with `CATAN_AUTH_REQUIRED=1`. The browser uses accounts in local development too; anonymous API compatibility is available locally unless this setting is enabled.

## What is implemented

Rooms are reusable for both multiplayer and private practice. Once the lineup is ready, the creator can launch 1–10 matches with a starting seed, shuffle it, or enable seat rotation. Seeds increase by one per match unless **Use the same seed for every match** is selected. This setting is independent of seat rotation; choose 4 or 8 rotated matches for balanced seat coverage. With the same seed and seat order, deterministic players produce identical matches. Participant identities, colours, exact bot versions and seat orders are frozen before enqueueing. Readiness persists across reruns; a changed bot or occupied seat clears all human readiness (simulation opponents are automatically ready). Room controls remain locked while a batch has pending/running matches.

Every room retains all its batches and recordings. Room/batch statistics group by player identity and bot version, not rotated seat, and show wins, recorded final points, roads, final settlements/cities, settlements built including setup, and development cards played. Expand each player for individual games, totals, averages and ranges. Completed matches alone enter the win-rate denominator; missing outcomes never become zero scores. New finished match summaries include final victory points; older recordings can supply only the public score they saved. Private room history and statistics retain owner-only access.

Replay pages include a batch match sidebar, a room link and same-seed/new-seed rematches for the creator when the unchanged lineup is ready. Switching recordings starts playback at the beginning. Rematching a rotated match preserves that match's original seat order. The creator can cancel queued matches while running ones finish normally.

The shared scheduler runs at most two isolated match processes and schedules pending batches round-robin, so one room cannot enqueue 100 jobs ahead of everyone else. The batch limit defaults to 10 (`CATAN_MAX_BATCH_SIZE`, 1–100); raising it does not increase concurrency. Unfinished jobs are marked interrupted after a server restart, preserving history and returning rooms to a reusable state.

In **My bots**, use **Edit** to change a saved player's name or description, or edit/replace its Python source and supply a new version name. Source changes create a new validated version; existing versions and match recordings retain their original implementation. **Remove** asks for confirmation and hides that version from the library and new selections. Original code is retained for existing recordings and queued matches, and removed version IDs cannot be reused. Open rooms selecting a removed version must select another before starting. Only the owner can edit or remove account-owned players.

- Match archive with queued/running/stopped/completed/failed status and reloadable links.
- Four-seat rooms, joining, persistent bot selections, ready/unready, selection resets, duplicate-seat/start protection and frozen participant/version metadata.
- Player-version creation, Python file/code upload, API validation diagnostics, details and duplicate-version protection. Every registered version contains a validated Player implementation.
- Background simulation in separate match processes supervised by a bounded two-thread pool, independent of browser lifetime.
- Atomic saved replay files and SQLite match metadata; restart recovery marks unfinished jobs as failed and retains completed recordings.
- Real recorded terrain, number tokens, robber, public player scores and achievements.
- A renderer for valid hex topology, roads, settlements, cities and ports. Older recordings with placeholder topology retain their labelled schematic; new games use the real hex board.
- Play/pause, speed, start/end, previous/next transition, previous/next turn, timeline drag, turn markers and journal jumps. Each viewer has independent playback state.
- Zoom, pan, reset, responsive layout, keyboard controls, error/empty states and downloadable replay JSON.
- Results shown on request or at the end: winner when recorded, termination reason, public piece/score totals and dice distribution.
- Public-only recordings and blocked anonymous private-state requests. Event payloads use an explicit allowlist, including removal of purchased development-card identity.

## Storage and boundaries

Match results include expandable development-card counts for each player (public `DevelopmentCardPlayed` events; victory point cards excluded). Below dice distribution, the report also plots all five resource holdings with one tab per player, line toggles and a position slider for exact counts. The chart preserves every recorded transition within each individual player turn, including trades/builds/discards, and separates setup. It uses finished spectator snapshots, never supplies these hands to bots, and works with existing recordings that contain resource snapshots. Older recordings without hands show an unavailable message.

Failed matches offer **Player error log** to signed-in participants. It shows only errors from their own seats: callback, phase/turn/decision, traceback, and (for invalid decisions) the returned action, available action types and guidance. Diagnostics are stored separately from public recordings and filtered by player ownership. Hosted process limits still apply. Earlier recordings may have no saved diagnostics; those display an explanatory message instead of a reconstructed trace.

`CATAN_DB_URL` defaults to `sqlite:///catan_platform.db` for rooms, implementation versions and the match catalog. `CATAN_REPLAY_DIR` overrides the recording directory; by default it is the SQLite filename plus `.replays` (for example `catan_platform.db.replays`). Keep both across restarts. Local state is ignored by Git.

`src/platform/server.py` handles requests, starts jobs and serves the static client. `RecordingSimulator` in `src/platform/recording.py` subscribes to native committed simulator transitions. It does not replace rules or bot decisions. Every recorded transition contains a copied public snapshot, so random access and backward seeking are exact without client-side Catan rules. The final recording is written before metadata advertises that it is available.

The client lives in `src/platform/static/`: `app.js` handles screens, `board.js` draws SVG, and `playback.js` handles timeline navigation. The older embedded `ui.py` is no longer served; its prior working-tree edits were retained.

Public replay format is documented in `src/platform/REPLAY_CONTRACT.md`. Old metadata-only SQL game entries and old event-only logs do not contain enough data for this viewer and are not represented as playable recordings.

## Player execution and remaining hosting work

The complete simulator is described in [Player API](PLAYER_API.md) and [Project structure](PROJECT_STRUCTURE.md). Code uploads implement one persistent Player class; each seat gets a separate instance/process. Import, protocol, lifecycle and initial-decision smoke checks run during validation. Old script-protocol versions remain stored but need a new compatible implementation version to run.

Submitted players have callback, message and resource limits. This is still a trusted local application: authenticated ownership and filesystem/network isolation for public untrusted hosting are not implemented. Direct in-process players are trusted and unbounded; the web runner uses process execution.

Every engine transition invokes the recording observer. The client consumes snapshots and does not reproduce Catan rules. Public production and trading events are retained; private audit files are stored separately and are not downloadable through replay endpoints. The winner's total score is revealed at completion; other players' hidden cards remain excluded.

## Verify

```powershell
python -m pytest -q
npm ci
npx playwright install chromium
npm run test:playback
npm run test:browser
```

Browser tests start an isolated server on port 8011 with temporary storage. They cover playback and seeking, desktop/mobile layouts, independent viewers, a four-participant room, text escaping/error recovery, and a complete geometry fixture. The fixture is synthetic and used only to verify rendering; it is not presented as a simulator-generated game. Screenshots and traces are written under `test-results/`.
# Private practice rooms and simulation opponents

Room creation offers Public or Private visibility. Private rooms and their match
metadata, state snapshots, and replay downloads are accessible only to the
creator's account; guessed links return 404 to other visitors. Legacy rooms stay
public. Access metadata is persisted in the additive `room_access` SQLite table.

Room creators can fill empty seats with Easy, Medium, or Hard simulation players,
change their difficulty, or remove them before a match starts. Human seats remain
controlled by their account owner. Built-in seats are ready automatically.

Valid saved uploads have a **Test your player** button. **Save and test your
player** in the upload dialog also opens this flow. Select a difficulty to create
a private room with your player and three opponents; choose the seed and start
the match from its lobby. The opponents use the same Player API and hidden-hand
restrictions as uploads. Compiled artifacts and build details are documented in
`src/platform/opponents/README.md`.
