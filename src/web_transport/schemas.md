# Web Transport Schemas

This file documents the minimal JSON shapes returned by the `web_transport` helpers.

## `GET /game/{id}/replay` (via `get_replay(sim)`) — Response

- `metadata`: object with `seed` and `game_id`.
- `events`: array of objects with keys: `sequence`, `type`, `game_id`, `turn_number`, `player_id`, `visibility`, `data`.

Example:

```json
{
  "metadata": { "seed": 42, "game_id": "game-42" },
  "events": [
    {"sequence": 0, "type": "GameStarted", "game_id": "game-42", "turn_number": 1, "player_id": "P1", "visibility": "PUBLIC", "data": {"seed": 42} }
  ]
}
```

## `GET /game/{id}/state?player=P1` (via `get_state(sim, PlayerId.P1)`) — Response

If `player` query string is provided, returns the `GameView`-derived snapshot for that player:

- `player_id`: string (e.g. "P1")
- `self.resources`: the requesting player's resource names and counts
- `self.victory_points`: the requesting player's score
- `opponents`: public totals and board information only. Entries contain `resource_count`, but never exact `resources` or development-card maps.
- `board.tiles`: tile objects with terrain, number, robber, and topology IDs.

Exact opponent hands must be inferred from the visible event stream. They are never returned by a player-specific state query.

If `player` is omitted, the public summary contains:

- `game_id`, `phase`, `turn_number`, `current_player`, `players` (each: `player_id`, `victory_points`).

These shapes are intentionally minimal for the first iteration; the front-end can request
more detailed views or follow-up endpoints as needed.
