import json

import pytest

from src.player.example import ExamplePlayer
from src.simulation.environment import CatanEnv
from src.simulation.simulator import Simulator, GameConfig
from src.simulator.cli import main
from src.simulator.terminal import board_text
from src.simulator.types.identifiers import PlayerId


@pytest.mark.parametrize('limit',[0,1,3])
def test_turn_limits_complete_setup_before_counting_normal_turns(limit):
    sim = Simulator(42,GameConfig(max_turns=limit))
    sim.register_players({pid:ExamplePlayer() for pid in PlayerId.all_players()})
    result = sim.run()
    sim.assert_invariants()
    assert result['status']=='stopped'
    assert all(len(p.settlements)>=2 for p in sim.game_state.players)
    events = sim.replay_recorder.export()['events']
    assert sum(e['type']=='DiceRolled' for e in events)==limit


class Memory(ExamplePlayer):
    def on_game_start(self, view):
        super().on_game_start(view)
        self.seen = []

    def on_event(self, event):
        self.seen.append(event)


def test_environment_matches_engine_and_preserves_events_privacy_and_reset():
    memory=Memory()
    env=CatanEnv(opponents=lambda pid:ExamplePlayer(),listener=memory,max_turns=5)
    view, info=env.reset(42)
    assert info.legal_actions and memory.seen
    assert all('resources' not in p for p in view.opponents)
    while info.result is None:
        action=memory.choose_action(view,info.legal_actions)
        view,reward,terminated,truncated,info=env.step(action)
    assert truncated and not terminated and reward==0
    sim=Simulator(42,GameConfig(max_turns=5))
    sim.register_players({pid:ExamplePlayer() for pid in PlayerId.all_players()})
    sim.run()
    assert env.sim.decisions==sim.decisions
    env.sim.assert_invariants()
    assert any(e.type=='GameEnded' for e in info.events)
    with pytest.raises(RuntimeError):env.step(action)
    view,info=env.reset(42)
    assert info.result is None and len(memory.seen)==len(info.events)


def test_environment_invalid_action_is_failure_not_a_win():
    env=CatanEnv(opponents=lambda pid:ExamplePlayer())
    with pytest.raises(RuntimeError):env.step({})
    env.reset(1)
    view,reward,terminated,truncated,info=env.step({'type':'END_TURN'})
    assert terminated and not truncated and reward==0
    assert info.result.status=='player_failed'


def test_environment_complete_game_and_custom_reward():
    policy=ExamplePlayer()
    env=CatanEnv(opponents=lambda pid:ExamplePlayer(),listener=policy,
                 reward_fn=lambda before,action,after,info: 7)
    view,info=env.reset(42)
    while info.result is None:
        view,reward,terminated,truncated,info=env.step(policy.choose_action(view,info.legal_actions))
        assert reward==7
    assert terminated and not truncated and info.result.status=='completed'
    env.sim.assert_invariants()


def test_cli_verbose_board_and_batch_json(tmp_path,capsys):
    starter='examples/my_player.py'
    assert main(['play','--player',starter,'--max-turns','0','--verbose','--color','always'])==0
    output=capsys.readouterr().out
    assert '\033[' in output and 'After initial placement' in output and 'SettlementBuilt' in output
    target=tmp_path/'results.json'
    assert main(['evaluate','--player',starter,'--games','4','--max-turns','0',
                 '--output','json','--results',str(target)])==0
    data=json.loads(capsys.readouterr().out)
    assert data==json.loads(target.read_text())
    assert data['statuses']=={'stopped':4}
    assert [r['player_id'] for r in data['runs']]==['P1','P2','P3','P4']
    assert [r['seed'] for r in data['runs']]==[42]*4


def test_board_plain_text_lists_all_tiles_and_ports():
    sim=Simulator(42)
    text=board_text(sim)
    assert '\033[' not in text
    assert all(t in text for t in sim.board.tiles)
    assert 'Ports:' in text
