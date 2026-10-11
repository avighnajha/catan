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

This installs this repository's `catansimulator` package and registers its `catansim` command in the active Python environment. `-e` means editable: the installation points to this checkout rather than copying its source. It is not a published PyPI package. After installation you can run `catansim` from your separate player project, passing a relative or absolute player path. Local tools have no web/database dependency. The legacy fallback `python -m src.simulator.cli` also works, but when running that command from an extracted SDK folder, move/remove the interface-only `src` folder first: it can shadow the installed full simulator. The new public Python import below handles the SDK folder automatically.

For Python scripts in a separate bot project, install the simulator into **that project's virtual environment**. For example, in PowerShell:

```powershell
cd C:\Users\avigh\Projects\catan-bots
.\.venv\Scripts\Activate.ps1
python -m pip install -e C:\Users\avigh\Projects\catan
python -c "from catansim import CatanEnv; print(CatanEnv)"
```

The installed distribution is named `catansimulator`, its CLI is `catansim`, and its public Python import is `catansim`. The SDK ZIP alone cannot run simulations. `from catansim import CatanEnv` also works beside the SDK's interface-only `src` folder; it connects that interface to the installed engine. Existing imports from `src.simulation.environment` remain compatible, but use the public import in new scripts. Refresh the editable installation after pulling these changes so Python discovers the new package.

## Updating

In the same activated environment, run:

```bash
catansim update
# Equivalent alias:
catansim --update
```

For an editable repository installation, this checks that the checkout is clean, pulls its tracked branch with `git pull --ff-only`, then refreshes the editable installation. It refuses local changes and divergent branches rather than resetting or overwriting them. Commit or stash changes yourself before retrying. For a copied/wheel installation, it reinstalls the latest package from the official GitHub repository. Updates require internet and Git; ordinary games do not. Restart running Python/IDE sessions afterwards. If a platform prevents replacing the running command executable, use `python -m src.simulator.cli update`.

Older installations do not yet have this command. To get it the first time, run `git pull --ff-only` inside your simulator checkout and `python -m pip install -e .` using your active environment.

## Run a player

Add **`--debug`** to `play` or `evaluate` to run your player in process and hit `breakpoint()` or IDE breakpoints. Callback timeouts are disabled in this mode. See [Prints, errors and breakpoints](#prints-errors-and-breakpoints) below for debugger setup.

```bash
catansim play --player examples/my_player.py --opponents medium --seed 42
catansim play --player my_player.py --opponents easy --seed 42 --debug
catansim play --player my_player.py --opponents easy --max-turns 0 --verbose
catansim play --player my_player.py --opponents hard --max-turns 20 --verbose --color always
catansim play --player my_player.py --seat P3 --output json --results result.json
catansim play --player my_player.py --replay match.json
```

`--max-turns` counts individual normal player turns, after all initial placements. Zero completes everyone's setup and stops before the first normal turn; one completes the first player's turn. Stopping at a limit produces `stopped`, not a winner. `--max-decisions` additionally bounds individual decisions, including setup, trade responses and discards; it defaults to 20,000. The engine also caps each turn at 200 decisions.

Summary output includes the outcome, reason, seed, your seat, winner, completed turns, scores and runtime. Scores are final local evaluation data and may include hidden victory points; they are not supplied as opponent hand information during play. Verbose output adds a terminal board before and after placement, plus public events in order, including exact trade exchanges. Resource-coloured hex labels show tile IDs, resource abbreviations, dice numbers and the robber (`R`). Settlements (`S`), cities (`C`) and roads use player colours; the accompanying ID lists and ports connect the drawing to the log. Colour is automatic in an interactive terminal; use `--color always` to force it or `--color never` for plain text. Wide terminals work best.

JSON output is suitable for scripts. Use `--results` with verbose mode to write JSON without mixing it with the human-readable log. `--replay` writes a spectator recording; `--audit` writes private debugging data including decisions and private events. Do not publish private audits. Player files use the same `Player` API as uploads and run in a separate process with a two-second callback timeout; use `--timeout 30` for slower local models. The new CLI uses trusted local execution without the hosted OS memory/CPU/process-count caps, so your virtual environment and model libraries can run. Hosted upload restrictions are unchanged. Exit code 1 means a player failed; code 2 means a CLI/setup error; limits are a normal exit with a stopped result.

The existing `python -m src.simulator.run` command still accepts zero or four `--player` files, replay/audit paths and a turn limit.

## Prints, errors and breakpoints

Your `print()` output (including during import and events) is streamed to **stderr** by default. This keeps `--output json` on stdout parseable. Use `--quiet-player` to suppress player prints, or `2> player.log` to save them. For example:

```bash
catansim play --player simple-strat/true_random.py --opponents easy --seed 20
catansim play --player my_player.py --output json > result.json
catansim play --player my_player.py --debug --seed 20
python -m pdb -m src.simulator.cli play --player my_player.py --debug --seed 20
```

Failures show the invalid action, decision ID, phase and available action types. Callback exceptions include local tracebacks. These details are also in JSON `failure_context` for failed matches. For example, returning just `{'type': 'TRADE'}` reports missing `give`, `receive` and `recipients`: choose another action or fill the template as described in `PLAYER_API.md`. Random players must handle all three templates (`TRADE`, `COUNTER`, `DISCARD`), not blindly return any option.

`--debug` runs your player in the CLI's process from its original file. Put `breakpoint()` in your callbacks for an interactive debugger, or configure your IDE to run module `src.simulator.cli` with arguments `play --player /path/to/my_player.py --debug --seed 20`. IDE breakpoints in both the player and engine work in this mode. Callback timeouts/process limits are disabled, so pausing does not fail the match. Game turn/decision limits still apply. Debug mode also works with `evaluate`, but pauses can occur in every match. Your current working directory stays unchanged, and the player file's directory is available for sibling imports. Without `--debug`, player code runs in a subprocess; ordinary IDE breakpoints in the CLI process will not stop that child.

This is trusted local debugging. The website still uses its original process limits and does not expose these local tracebacks or private decisions. Python's `CatanEnv` already runs in process and can be debugged directly without a CLI flag.

## Compare versions across games

```bash
catansim evaluate --player my_player.py --opponents medium --games 100 --seed 42 --results evaluation.json
```

`--games` is the total match count. Seats rotate P1, P2, P3, P4; each group of four uses the same seed, then the seed increments. Multiples of four give balanced seat coverage. Each match constructs fresh players. Output separates completed games, limits and failures, reports wins out of completed games, average own score across all runs, and counts by seat. The JSON contains every individual result. Compare versions with identical seeds, opponents and limits; a small sample is not reliable evidence of improvement.

## Python games and experiments

Use `CatanEnv` with a **player factory** to run your existing Player automatically. All four players receive the same `choose_action`, lifecycle and separate `on_event` callbacks as CLI games. The factory is a class or zero-argument function that creates a fresh Player on every `reset`; do not reuse one instance across games.

```python
from catansim import CatanEnv
from my_player import MyPlayer  # Your own module/class, not a built-in strategy.

env = CatanEnv(player_factory=MyPlayer, opponents='easy', player_id='P1')
view, info = env.reset(seed=20)
result = env.run()
print(result.status, result.winner, result.reason)
```

Automatic mode's `reset` creates the board and all players, delivers game-start callbacks/events, and stops **before initial placement decisions**. Inspect `view.board`, then advance at whichever level you need:

| Method | What it finishes | Returns |
| --- | --- | --- |
| `run_step()` | One pending decision by whichever seat must act, including placement, discard or trade responses | `(view, info)` |
| `run_setup()` | All remaining initial placements; no normal turn decisions | `(view, info)` |
| `run_turn()` | The current active player's normal turn, including other players' responses | `(view, info)` |
| `run_round()` | The remainder of the current round, ending after P4's turn | `(view, info)` |
| `run()` | The entire remaining game, or a configured limit/failure | Immutable result |

`run_turn()` and `run_round()` finish setup first if needed. They finish the current turn/round from wherever you paused. For example, `run_turn()` from the start of P1's turn leaves P2 to act; the following `run_round()` finishes P2, P3 and P4, leaving P1 at the start of round two. Calling `run_round()` at a round boundary runs the next complete round. One decision is not necessarily one turn, and its acting seat may differ from the active turn owner.

```python
env.reset(seed=20)
view, info = env.run_setup()
view, info = env.run_step()   # Normally P1 rolls; this can create discard decisions.
view, info = env.run_turn()   # Finish the rest of P1's turn.
view, info = env.run_round()  # Finish P2, P3 and P4.
print(info.round_number, info.turn_number, info.acting_player)
print(view.self.resources)
for event in info.events:
    print(event.type, event.data)
result = env.run()           # Resume the same game to completion.
```

Every runner stops early for victory, a player failure or a configured limit. Inspect `info.result` after partial runs; it is `None` while the game continues. Once ended, automatic runners return the existing result without calling players again. Call `reset` for a fresh game. `max_turns=0` completes setup only; normal turns, not rounds, count toward this limit.

Returned views always belong to your configured `player_id` and hide opponents' exact hands. `info.acting_player` identifies the next decision's seat (`None` when ended). `info.legal_actions` is empty when another seat must act, so another player's private choices are not exposed. `info.events` contains visible events since the previous snapshot return; callbacks still receive them as they happen. `info.phase`, `turn_number`, `round_number` and `decision_id` describe the current position. The local `env.sim` is available for trusted debugging/audits, but is engine state, not a privacy-filtered observation.

To run 100 games from your own Python code:

```python
from collections import Counter
from catansim import CatanEnv, thaw
from my_player import MyPlayer

runs = []
for index in range(100):
    seat = f'P{index % 4 + 1}'
    seed = 20 + index // 4
    env = CatanEnv(player_factory=MyPlayer, player_id=seat, opponents='medium')
    env.reset(seed=seed)
    runs.append(dict(thaw(env.run()), seed=seed, player_id=seat))

completed = [r for r in runs if r['status'] == 'completed']
wins = sum(r['winner'] == r['player_id'] for r in completed)
print('Statuses:', Counter(r['status'] for r in runs))
print('Wins:', wins, 'out of', len(completed), 'completed games')
```

This rotates seats and uses the same seed for each group of four games, matching CLI evaluation. Limits and failures are reported separately from completed losses. The SDK ZIP and repository include runnable scripts: `examples/local_games.py` for batches and `examples/local_steps.py` for inspection. Replace their `MyPlayer` import with your own. After installing the simulator, run:

```bash
python examples/local_games.py --games 100 --seed 20 --opponents medium > results.json
python examples/local_steps.py
```

These calls run locally in process with no account, server or database. Breakpoints and prints work directly; there are no callback timeouts or hosted OS caps. Only run trusted local players. Game limits still apply. Custom opponents can be supplied as `opponents=lambda seat: MyOpponent()`; create a fresh instance for each seat. Built-in opponents require CPython 3.10 or 3.12. For parallel experiments use separate environment instances in separate processes.

## Python decision environment for RL

`CatanEnv` lets a Python training or debugging program choose each action directly. It uses the same rules engine as CLI and hosted games and runs locally in process. It is a lightweight Python interface with Gym-style return values, not a Gymnasium subclass: no numeric observation encoding, fixed action space, neural network or learning algorithm is supplied.

```python
from src.player import Player
from catansim import CatanEnv

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

Omit `player_factory` for this external-control mode. `step(action)` supplies your decision and advances opponents automatically; it differs from automatic mode's `run_step()`, which calls exactly one seat's Player callback. Automatic runners require a `player_factory`, and `step(action)` requires external control; mixing the two modes raises an explanatory error. Neither mode supplies a learning algorithm or reward encoding beyond the defaults below.

Views/actions/events remain immutable and opponents' exact hands remain private. A completed match or player failure sets `terminated`; a configured limit sets `truncated`. Check `info.result.status` to distinguish failure from victory. Illegal actions end the episode as `player_failed`, just as in ordinary matches. After either flag, call `reset` for another episode; stepping an ended episode raises an error. A failure during reset can already produce a non-null result with no legal actions.

Default reward is +1 for your win, -1 for another player's win, and 0 otherwise (including limits and failures). For custom rewards, pass `reward_fn(previous_view, action, next_view, info)` returning a number. Reward functions and learners are user-provided trusted code; do not quietly interpret a failed opponent as a win.

For custom opponents, pass a factory instead of a difficulty: `CatanEnv(opponents=lambda seat: MyOpponent())`. It must create a fresh `Player` for each opponent seat. This works without the compiled opponents on other Python versions. Run independent environment instances in separate worker processes for parallel training. In-process code has no callback timeout, so use trusted local implementations. Advanced models can later be wrapped in a normal `Player` for CLI evaluation and website uploads, subject to their execution limits.
