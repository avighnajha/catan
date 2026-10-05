# Local testing and training

These tools run on your computer. They do not call the hosted backend, require an account, or upload your code. The SDK ZIP contains the interface and starter; install the full simulator separately to run games.

## Setup

Install **CPython 3.10 or 3.12** and Git. The supplied compiled opponents currently support these two Python versions. From a terminal:

```bash
git clone https://github.com/avighnajha/catan.git
cd catan
python -m venv .venv
```

Activate with `.venv\Scripts\Activate.ps1` in PowerShell, or `source .venv/bin/activate` on Linux/macOS. Then:

```bash
python -m pip install -e .
catansim --help
```

This is an installation from the repository, not a published PyPI package. Local tools have no web/database dependency. Use `python -m src.simulator.cli` in place of `catansim` if needed. Keep your player project outside the downloaded SDK's `src` folder when using the installed simulator, so that the interface-only folder does not shadow the full installation.

## Run a player

```bash
catansim play --player examples/my_player.py --opponents medium --seed 42
catansim play --player my_player.py --opponents easy --max-turns 0 --verbose
catansim play --player my_player.py --opponents hard --max-turns 20 --verbose --color always
catansim play --player my_player.py --seat P3 --output json --results result.json
catansim play --player my_player.py --replay match.json
```

`--max-turns` counts individual normal player turns, after all initial placements. Zero completes everyone's setup and stops before the first normal turn; one completes the first player's turn. Stopping at a limit produces `stopped`, not a winner. `--max-decisions` additionally bounds individual decisions, including setup, trade responses and discards; it defaults to 20,000. The engine also caps each turn at 200 decisions.

Summary output includes the outcome, reason, seed, your seat, winner, completed turns, scores and runtime. Scores are final local evaluation data and may include hidden victory points; they are not supplied as opponent hand information during play. Verbose output adds a terminal board before and after placement, plus public events in order, including exact trade exchanges. Resource-coloured hex labels show tile IDs, resource abbreviations, dice numbers and the robber (`R`). Settlements (`S`), cities (`C`) and roads use player colours; the accompanying ID lists and ports connect the drawing to the log. Colour is automatic in an interactive terminal; use `--color always` to force it or `--color never` for plain text. Wide terminals work best.

JSON output is suitable for scripts. Use `--results` with verbose mode to write JSON without mixing it with the human-readable log. `--replay` writes a spectator recording; `--audit` writes private debugging data including decisions and private events. Do not publish private audits. Player files use the same `Player` API as uploads and run in a separate process with a two-second callback timeout; use `--timeout 30` for slower local models. The new CLI uses trusted local execution without the hosted OS memory/CPU/process-count caps, so your virtual environment and model libraries can run. Hosted upload restrictions are unchanged. Exit code 1 means a player failed; code 2 means a CLI/setup error; limits are a normal exit with a stopped result.

The existing `python -m src.simulator.run` command still accepts zero or four `--player` files, replay/audit paths and a turn limit.

## Compare versions across games

```bash
catansim evaluate --player my_player.py --opponents medium --games 100 --seed 42 --results evaluation.json
```

`--games` is the total match count. Seats rotate P1, P2, P3, P4; each group of four uses the same seed, then the seed increments. Multiples of four give balanced seat coverage. Each match constructs fresh players. Output separates completed games, limits and failures, reports wins out of completed games, average own score across all runs, and counts by seat. The JSON contains every individual result. Compare versions with identical seeds, opponents and limits; a small sample is not reliable evidence of improvement.

## Python decision environment

`CatanEnv` lets a Python training or debugging program choose each action directly. It uses the same rules engine as CLI and hosted games and runs locally in process. It is a lightweight Python interface with Gym-style return values, not a Gymnasium subclass: no numeric observation encoding, fixed action space, neural network or learning algorithm is supplied.

```python
from src.player import Player
from src.simulation.environment import CatanEnv

class EventMemory(Player):
    def on_game_start(self, view):
        self.events_seen = 0

    def on_event(self, event):
        self.events_seen += 1

memory = EventMemory()
env = CatanEnv(opponents='medium', player_id='P1',
               max_turns=20, listener=memory)
view, info = env.reset(seed=42)

while info.result is None:
    options = info.legal_actions
    # Interface demonstration only: fill templates when required.
    action = next((a for a in options if a.type == 'END_TURN'), options[0])
    if action.type == 'DISCARD':
        remaining = action.count
        resources = {}
        for resource, held in view.self.resources.items():
            take = min(held, remaining)
            if take:
                resources[resource] = take
                remaining -= take
        action = {'type': 'DISCARD', 'resources': resources}
    elif action.type == 'COUNTER':
        action = next(a for a in options if a.type == 'REJECT')
    elif action.type == 'TRADE':
        action = next(a for a in options if a.type == 'END_TURN')

    previous_view = view
    view, reward, terminated, truncated, info = env.step(action)
    # Feed (previous_view, action, reward, view, flags) to your learner here.
    if terminated or truncated:
        print(info.result)
        break
```

`reset` starts a fresh match and advances opponents to your first decision. `step` applies one action, delivers committed events, and advances opponents until your next decision or the match ends. Your decisions can include trade responses and discards during other players' turns. `info.legal_actions` contains current legal actions; templates follow the same rules in `PLAYER_API.md`. `info.decision_id` identifies the decision, and `info.events` contains only events visible to your seat since the previous return. The optional listener receives separate lifecycle and `on_event` callbacks as those events happen; its `choose_action` is not used. Listener memory should reset in `on_game_start`.

Views/actions/events remain immutable and opponents' exact hands remain private. A completed match or player failure sets `terminated`; a configured limit sets `truncated`. Check `info.result.status` to distinguish failure from victory. Illegal actions end the episode as `player_failed`, just as in ordinary matches. After either flag, call `reset` for another episode; stepping an ended episode raises an error. A failure during reset can already produce a non-null result with no legal actions.

Default reward is +1 for your win, -1 for another player's win, and 0 otherwise (including limits and failures). For custom rewards, pass `reward_fn(previous_view, action, next_view, info)` returning a number. Reward functions and learners are user-provided trusted code; do not quietly interpret a failed opponent as a win.

For custom opponents, pass a factory instead of a difficulty: `CatanEnv(opponents=lambda seat: MyOpponent())`. It must create a fresh `Player` for each opponent seat. This works without the compiled opponents on other Python versions. Run independent environment instances in separate worker processes for parallel training. In-process code has no callback timeout, so use trusted local implementations. Advanced models can later be wrapped in a normal `Player` for CLI evaluation and website uploads, subject to their execution limits.
