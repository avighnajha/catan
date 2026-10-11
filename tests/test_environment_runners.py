import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from catansim import CatanEnv, Player, thaw
from src.player.example import ExamplePlayer
from src.simulation import Simulator
from src.simulation.simulator import GameConfig
from src.simulator.types.identifiers import PlayerId
from tests.engine_helpers import grant


def environment(**kwargs):
    return CatanEnv(player_factory=ExamplePlayer,
                    opponents=lambda seat: ExamplePlayer(), **kwargs)


def test_setup_turn_and_partial_round_boundaries():
    env = environment(max_turns=8)
    view, info = env.reset(20)
    assert info.phase == 'SETUP_SETTLEMENT' and info.decision_id == 0
    view, info = env.run_step()
    assert info.decision_id == 1 and info.phase == 'SETUP_ROAD'
    view, info = env.run_setup()
    assert info.decision_id == 16 and info.phase == 'PRE_ROLL'
    assert all(len(p.settlements) == 2 for p in env.sim.game_state.players)
    view, info = env.run_turn()
    assert info.turn_number == 2 and info.acting_player == 'P2'
    assert not info.legal_actions  # Never leak another seat's private options.
    view, info = env.run_round()
    assert info.turn_number == 5 and info.round_number == 2
    assert info.acting_player == 'P1'
    assert sum(e.type == 'TurnEnded' for e in info.events) == 3
    view, info = env.run_round()
    assert info.result.status == 'stopped'
    assert env.run() == info.result
    assert env.run_step()[1].result == info.result
    env.sim.assert_invariants()


@pytest.mark.parametrize('runner', ['run_turn', 'run_round'])
def test_turn_and_round_finish_setup_automatically(runner):
    env = environment(max_turns=8)
    env.reset(20)
    view, info = getattr(env, runner)()
    assert info.turn_number == (2 if runner == 'run_turn' else 5)


def test_runners_preserve_engine_decisions_events_and_fresh_players():
    instances = []

    class Tracked(ExamplePlayer):
        def __init__(self):
            instances.append(self)
            self.events = []

        def on_event(self, event): self.events.append(event)
        def on_game_end(self, result): self.result = result

    env = CatanEnv(player_factory=Tracked, opponents=lambda seat: ExamplePlayer(), max_turns=7)
    env.reset(42)
    result = env.run()
    sim = Simulator(42, GameConfig(max_turns=7))
    sim.register_players({p: ExamplePlayer() for p in PlayerId.all_players()})
    sim.run()
    assert thaw(result) == sim.result and env.sim.decisions == sim.decisions
    assert instances[0].result == result
    assert any(e.type == 'GameEnded' for e in instances[0].events)
    env.reset(42)
    assert len(instances) == 2 and instances[0] is not instances[1]
    assert env.run() == result


def test_step_can_process_opponent_trade_response_without_ending_active_turn():
    env = environment(max_turns=8)
    env.reset(20)
    env.run_setup()
    sim = env.sim
    sim.apply_action(sim.active, {'type': 'ROLL'})
    while sim.stage != 'PLAYING': sim.step()
    grant(sim, sim.active, {'WOOD': 1})
    sim.apply_action(sim.active, {'type': 'TRADE', 'give': {'WOOD': 1},
                                'receive': {'ORE': 1}, 'recipients': ['P2']})
    before = sim.decision_number
    view, info = env.run_step()
    assert sim.decisions[-1]['player_id'] == 'P2'
    assert info.decision_id == before + 1 and info.turn_number == 1
    assert view.player_id == 'P1' and all('resources' not in p for p in view.opponents)
    env.run_turn()
    assert sim.game_state.turn_state.turn_number == 2


def test_limits_and_failures_stop_runners():
    env = environment(max_turns=0)
    env.reset(20)
    assert env.run_setup()[1].result.status == 'stopped'
    assert env.sim.decision_number == 16
    env = environment(max_decisions=1)
    env.reset(20)
    assert env.run_round()[1].result.status == 'stopped'
    assert env.sim.decision_number == 1

    class Broken(Player):
        def choose_action(self, view, options): raise ValueError('broken player')

    env = CatanEnv(player_factory=Broken, opponents=lambda seat: ExamplePlayer())
    env.reset(20)
    assert env.run_turn()[1].result.status == 'player_failed'
    assert 'broken player' in env.sim.failures[0]['error']


def test_full_game_and_failure_during_reset():
    env = environment()
    env.reset(42)
    assert env.run().status == 'completed'
    env.sim.assert_invariants()

    class BrokenStart(Player):
        def on_game_start(self, view): raise ValueError('cannot start')

    env = CatanEnv(player_factory=BrokenStart, opponents=lambda seat: ExamplePlayer())
    view, info = env.reset(20)
    assert info.result.status == 'player_failed' and not info.legal_actions
    assert env.run_round()[1].result == info.result
    assert env.run() == info.result


def test_modes_require_reset_and_do_not_mix_automatic_and_external_decisions():
    env = environment()
    with pytest.raises(RuntimeError, match='reset'): env.run()
    env.reset()
    with pytest.raises(RuntimeError, match='external control'): env.step({})
    external = CatanEnv(opponents=lambda seat: ExamplePlayer())
    external.reset()
    with pytest.raises(RuntimeError, match='player_factory'): external.run_round()
    invalid = CatanEnv(player_factory=lambda: object())
    with pytest.raises(TypeError, match='Player'): invalid.reset()
    shared = ExamplePlayer()
    invalid = CatanEnv(player_factory=lambda: shared, opponents=lambda seat: shared)
    with pytest.raises(ValueError, match='own player instance'): invalid.reset()


def test_public_import_from_bot_project_with_standalone_sdk(tmp_path):
    root = Path(__file__).resolve().parents[1]
    sdk = tmp_path / 'src/player'
    sdk.mkdir(parents=True)
    (tmp_path / 'src/__init__.py').write_text('')
    for name in ['__init__.py', 'interface.py', 'types.py']:
        shutil.copy(root / 'src/player' / name, sdk / name)
    code = '''
from src.player import Player
from catansim import CatanEnv
from src.player.example import ExamplePlayer
env = CatanEnv(player_factory=ExamplePlayer, opponents='easy', max_turns=0)
env.reset(20)
assert env.run().status == 'stopped'
assert 'sqlalchemy' not in __import__('sys').modules
'''
    # example.py is not part of the SDK; use the project's minimal starter.
    shutil.copy(root / 'examples/my_player.py', tmp_path / 'my_player.py')
    code = code.replace('from src.player.example import ExamplePlayer',
                        'from my_player import MyPlayer as ExamplePlayer')
    subprocess.run([sys.executable, '-c', code], cwd=tmp_path,
                   env=dict(os.environ, PYTHONPATH=str(root)), check=True, timeout=30)
