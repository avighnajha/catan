"""Check exported schemas against real engine payloads and standalone SDK."""
import io
import subprocess
import sys
import zipfile
from typing import get_args, get_type_hints

from fastapi.testclient import TestClient
from src import player
from src.player import types
from src.player.example import ExamplePlayer
from src.simulation import Simulator
from src.simulator.types.identifiers import PlayerId


def check_action_shape(value, union):
    schemas = [schema for schema in get_args(union)
               if value['type'] in get_args(get_type_hints(schema)['type'])]
    assert len(schemas)==1, value
    schema=schemas[0]
    assert set(value)==set(schema.__required_keys__), (schema,value)


def test_action_schemas_match_real_choices_and_submitted_actions():
    sim=Simulator(41)
    sim.register_players({pid:ExamplePlayer() for pid in PlayerId.all_players()})
    sim.start_game()
    while sim.result is None:
        for option in sim.available_actions():
            check_action_shape(option,types.ActionOption)
        sim.step()
    assert sim.result['status']=='completed'
    for decision in sim.decisions:
        check_action_shape(decision['action'],types.Action)
    # Negotiation templates and filled actions must be different shapes.
    for option in ({'type':'TRADE'},{'type':'COUNTER'},{'type':'DISCARD','count':2}):
        check_action_shape(option,types.ActionOption)
    for action in ({'type':'TRADE','recipients':['P2'],'give':{'WOOD':1},'receive':{'ORE':1}},
                   {'type':'COUNTER','give':{'ORE':1},'receive':{'WOOD':1}},
                   {'type':'DISCARD','resources':{'WOOD':2}}):
        check_action_shape(action,types.Action)


def protocol_fields(schema):
    fields=set()
    for base in schema.__mro__:
        fields.update(k for k,v in vars(base).items() if isinstance(v,property))
    return fields


def test_snapshot_schemas_match_observation_without_opponent_hand_leaks():
    sim=Simulator(42)
    view=sim.build_view_for_player(PlayerId.P1)
    assert set(view)==protocol_fields(types.PlayerView)
    assert set(view.board)==protocol_fields(types.Board)
    for name,schema in (('tiles',types.Tile),('vertices',types.Vertex),
                        ('edges',types.Edge),('ports',types.Port)):
        assert all(set(item)==protocol_fields(schema) for item in view.board[name].values())
    assert set(view.self)==protocol_fields(types.SelfState)
    assert all(set(p)==protocol_fields(types.OpponentState) for p in view.opponents)
    assert 'resources' not in protocol_fields(types.OpponentState)
    assert set(view.turn)==protocol_fields(types.TurnState)
    assert all(getattr(player,name) is getattr(types,name) for name in types.__all__)


def test_sdk_imports_standalone_without_simulator_or_external_dependencies(tmp_path):
    from src.platform.server import app
    archive=zipfile.ZipFile(io.BytesIO(TestClient(app).get('/player-sdk.zip').content))
    archive.extractall(tmp_path)
    script = "import sys; from src.player import Player, Board, Action, PlayerView; from examples.my_player import MyPlayer; assert issubclass(MyPlayer, Player); assert not any(k.startswith('src.simulation') for k in sys.modules)"
    completed=subprocess.run([sys.executable,'-S','-c',script],cwd=tmp_path,
                             capture_output=True,text=True,timeout=10)
    assert completed.returncode==0,completed.stderr
