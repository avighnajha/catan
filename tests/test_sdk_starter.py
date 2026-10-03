"""The downloadable starter is self-contained and survives real decisions."""
import io
from pathlib import Path
import zipfile
from fastapi.testclient import TestClient
from src.player.example import ExamplePlayer
from src.player.process import ProcessPlayer
from src.player import freeze
from src.simulation import Simulator
from src.simulator.types.identifiers import PlayerId


def test_starter_runs_a_complete_match_through_the_upload_protocol():
    code = Path('examples/my_player.py').read_text(encoding='utf-8')
    player = ProcessPlayer(code)
    try:
        sim = Simulator(seed=41)
        sim.register_players({pid: player if pid == PlayerId.P1 else ExamplePlayer()
                              for pid in PlayerId.all_players()})
        sim.run()
        sim.assert_invariants()
        assert sim.result['status'] == 'completed', sim.result
        hand = {'WOOD': 2, 'ORE': 4}
        action = player.choose_action(freeze({'self': {'resources': hand}}),
                                      freeze([{'type': 'DISCARD', 'count': 3}]))
        assert set(action) == {'type', 'resources'} and action['type'] == 'DISCARD'
        assert sum(action['resources'].values()) == 3
        assert all(0 < count <= hand[resource] for resource, count in action['resources'].items())
    finally:
        player.close()


def test_sdk_archive_contains_only_the_interface_and_minimal_starter():
    from src.platform.server import app
    response = TestClient(app).get('/player-sdk.zip')
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert 'src/player/example.py' not in archive.namelist()
        assert 'src/player/interface.py' in archive.namelist()
        starter = archive.read('examples/my_player.py').decode()
        assert 'class MyPlayer(Player):' in starter
        assert 'ExamplePlayer' not in starter
