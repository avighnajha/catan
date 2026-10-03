"""Private room access and built-in worker integration."""
import uuid
from fastapi.testclient import TestClient
from src.platform.builtin_players import load_player
from src.player import Player


def account(client):
    suffix = uuid.uuid4().hex
    response = client.post('/auth/register', json={'username': suffix[:20],
        'email': suffix+'@example.com', 'password': 'test-password-long'})
    assert response.status_code == 200
    return {'Authorization': 'Bearer '+response.json()['token']}


def test_private_room_and_replay_are_owner_only(monkeypatch):
    from src.platform import server
    monkeypatch.setattr(server, 'AUTH_REQUIRED', True)
    client = TestClient(server.app)
    owner, stranger = account(client), account(client)
    room = client.post('/rooms?private=true', headers=owner).json()['room']
    rid = room['room_id']
    assert room['private']
    for headers in ({}, stranger):
        assert client.get('/rooms/'+rid, headers=headers).status_code == 404
        assert rid not in [r['room_id'] for r in client.get('/rooms', headers=headers).json()['rooms']]
        assert client.post('/rooms/'+rid+'/builtin-bot', headers=headers,
                           json={'seat': 1, 'difficulty': 'easy'}).status_code in (401,404)
    assert client.post('/rooms/'+rid+'/builtin-bot', headers=owner,
                       json={'seat': 1, 'difficulty': 'hard'}).status_code == 200
    game_id = 'game-'+uuid.uuid4().hex
    server.store.save_metadata({'game_id': game_id, 'private': True, 'owner_id': room['owner_id'],
                               'status': 'queued', 'created_at': '2026-10-03'})
    for headers in ({}, stranger):
        assert client.get('/games/'+game_id, headers=headers).status_code == 404
        assert client.get('/game/'+game_id+'/replay', headers=headers).status_code == 404
        assert client.get('/game/'+game_id+'/state', headers=headers).status_code == 404
        assert game_id not in [g['game_id'] for g in client.get('/games', headers=headers).json()['games']]
    assert client.get('/game/'+game_id+'/replay', headers=owner).status_code == 409


def test_test_player_creates_three_ready_opponents(monkeypatch):
    from src.platform import server
    monkeypatch.setattr(server, 'AUTH_REQUIRED', True)
    client = TestClient(server.app)
    owner = account(client)
    bot = client.post('/bots/upload', headers=owner, json={'bot_name': 'Practice', 'bot_version': 'v1',
        'bot_code': 'from src.player import Player\nclass P(Player):\n def choose_action(self,view,options): return options[0]\n'}).json()
    response = client.post('/bots/test', headers=owner, json={'bot_id': bot['bot_id'], 'difficulty': 'medium'})
    assert response.status_code == 200, response.text
    room = response.json()['room']
    assert room['private'] and all(s['ready'] for s in room['seats'])
    assert [s['bot_runner'] for s in room['seats'][1:]] == ['builtin-medium-v1']*3
    assert client.post('/rooms/'+room['room_id']+'/builtin-bot', headers=owner,
                       json={'seat': 0, 'difficulty': 'easy'}).status_code == 400


def test_compiled_players_implement_the_public_interface():
    for level in ('easy','medium','hard'):
        assert isinstance(load_player(level), Player)
