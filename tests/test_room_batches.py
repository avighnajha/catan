import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from src.platform import server
from src.platform.replay_store import ReplayStore
from src.platform.room_batches import FairMatchQueue, aggregate
from src.platform.match_worker import run_job
from src.platform.database import RoomAccess
from tests.test_builtin_rooms import account

CODE='from src.player import Player\nclass P(Player):\n def choose_action(self,view,options): return options[0]\n'


class CaptureQueue:
    def __init__(self): self.jobs=[]
    def submit_batch(self,callback,jobs): self.jobs.extend((callback,args) for args in jobs)


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(server,'AUTH_REQUIRED',True)
    queue=CaptureQueue()
    monkeypatch.setattr(server,'workers',queue)
    return TestClient(server.app),queue


def ready_room(client,private=False):
    owner=account(client)
    bot=client.post('/bots/upload',headers=owner,json={'bot_name':'Batch player','bot_version':'v1','bot_code':CODE}).json()
    room=client.post('/rooms',headers=owner,params={'room_name':'Batch table','private':private}).json()['room']
    rid=room['room_id'];name=room['seats'][0]['player_name']
    client.post(f'/rooms/{rid}/attach-bot',headers=owner,json={'player_name':name,'bot_name':bot['bot_id']})
    for seat in range(1,4):
        assert client.post(f'/rooms/{rid}/builtin-bot',headers=owner,json={'seat':seat,'difficulty':'easy'}).status_code==200
    client.post(f'/rooms/{rid}/ready',headers=owner,json={'player_name':name})
    return rid,owner


def start(client,rid,owner,**kwargs):
    response=client.post(f'/rooms/{rid}/start-game',headers=owner,json={'seed':20,**kwargs})
    assert response.status_code==200,response.text
    return response.json()


def finish(game_id,status='completed',winner='P1',summary=True):
    game=server.store.metadata(game_id)
    game.update(status=status,winner=winner if status=='completed' else None)
    if summary:
        game['summary']=[{'player_id':p['player_id'],'points':10 if p['player_id']==winner else 7,
            'roads':8,'settlements':3,'cities':2,'settlements_built':5,'dev_cards_played':3,
            'score_visibility':'final'} for p in game['participants']]
    server.store.save_metadata(game)
    server.release_room(game['room_id'])
    return game


def test_batch_freezes_lineup_rotates_seats_and_uses_consecutive_seeds(setup):
    client,queue=setup;rid,owner=ready_room(client)
    original=client.get(f'/rooms/{rid}',headers=owner).json()['room']['seats']
    batch=start(client,rid,owner,count=3,rotate_seats=True)
    games=[server.store.metadata(gid) for gid in batch['game_ids']]
    assert [g['seed'] for g in games]==[20,21,22]
    assert [g['batch_index'] for g in games]==[1,2,3]
    assert [g['room_match_number'] for g in games]==[1,2,3]
    for index,game in enumerate(games):
        expected=original[index:]+original[:index]
        assert [(p['name'],p['bot_id'],p['color']) for p in game['participants']]==[(s['player_name'],s['bot_runner'],s['color']) for s in expected]
        assert [p['player_id'] for p in game['participants']]==['P1','P2','P3','P4']
    assert len(queue.jobs)==3
    assert client.get(f'/rooms/{rid}',headers=owner).json()['room']['seats']==original
    assert client.post(f'/rooms/{rid}/start-game',headers=owner,json={}).status_code==400
    assert client.post(f'/rooms/{rid}/builtin-bot',headers=owner,json={'seat':1,'difficulty':'hard'}).status_code==400


@pytest.mark.parametrize('rotate_seats', [False, True])
def test_batch_can_keep_seed_constant_independently_of_seat_rotation(setup,rotate_seats):
    client,queue=setup;rid,owner=ready_room(client,True)
    # The highest valid seed also works in a batch when it is not incremented.
    batch=start(client,rid,owner,seed=2**31-1,count=3,keep_seed=True,rotate_seats=rotate_seats)
    games=[server.store.metadata(gid) for gid in batch['game_ids']]
    assert [g['seed'] for g in games]==[2**31-1]*3
    assert all(g['keep_seed'] for g in games) and len(queue.jobs)==3
    assert [g['participants'][0]['room_seat'] for g in games]==([1,2,3] if rotate_seats else [1,1,1])
    room=client.get(f'/rooms/{rid}',headers=owner).json()['room']
    assert room['batches'][0]['keep_seed'] is True


def test_private_room_deletion_keeps_recordings_private_and_bots_saved(setup):
    client,_=setup;rid,owner=ready_room(client,True);stranger=account(client)
    batch=start(client,rid,owner,count=2)
    for gid in batch['game_ids']: finish(gid)
    game=server.store.metadata(batch['game_id'])
    recording={'metadata':game,'result':{'status':'completed'},'frames':[]}
    server.store.finish(game['game_id'],recording,{**game,'replay_available':True})
    bots=client.get('/bots',headers=owner).json()
    stats=client.get('/account/stats',headers=owner).json()
    assert client.delete(f'/rooms/{rid}',headers=owner).status_code==200
    assert client.get(f'/rooms/{rid}',headers=owner).status_code==404
    assert rid not in [r['room_id'] for r in client.get('/rooms',headers=owner).json()['rooms']]
    with server.room_service.db_manager as session:
        assert session.get(RoomAccess,rid) is None
    assert client.get('/bots',headers=owner).json()==bots
    assert client.get('/account/stats',headers=owner).json()==stats
    assert client.get(f"/game/{game['game_id']}/replay",headers=owner).json()==recording
    navigation=client.get(f"/games/{game['game_id']}/batch",headers=owner).json()
    assert navigation['room_id'] is None and not navigation['can_rematch']
    assert len(navigation['matches'])==2
    for headers in ({},stranger):
        assert client.get(f"/games/{game['game_id']}",headers=headers).status_code==404
        assert client.get(f"/game/{game['game_id']}/replay",headers=headers).status_code==404
        assert client.get(f"/games/{game['game_id']}/batch",headers=headers).status_code==404
    assert client.delete(f'/rooms/{rid}',headers=owner).status_code==404


def test_private_room_deletion_checks_ownership_and_active_batches(setup):
    client,_=setup;rid,owner=ready_room(client,True);stranger=account(client)
    for headers in ({},stranger):
        assert client.delete(f'/rooms/{rid}',headers=headers).status_code==404
    public,host=ready_room(client)
    assert client.delete(f'/rooms/{public}',headers=host).status_code==403
    batch=start(client,rid,owner,count=2)
    assert client.delete(f'/rooms/{rid}',headers=owner).status_code==409
    first=server.store.metadata(batch['game_id']);first['status']='running';server.store.save_metadata(first)
    client.post(f"/rooms/{rid}/batches/{batch['batch_id']}/cancel",headers=owner)
    assert client.delete(f'/rooms/{rid}',headers=owner).status_code==409
    finish(first['game_id'])
    assert client.delete(f'/rooms/{rid}',headers=owner).status_code==200


def test_cancel_preserves_running_match_and_room_can_be_reused(setup,monkeypatch):
    client,_=setup;rid,owner=ready_room(client,True)
    batch=start(client,rid,owner,count=3)
    first=server.store.metadata(batch['game_ids'][0]);first['status']='running';server.store.save_metadata(first)
    response=client.post(f"/rooms/{rid}/batches/{batch['batch_id']}/cancel",headers=owner)
    assert response.json()['cancelled']==2
    assert server.store.metadata(first['game_id'])['status']=='running'
    cancelled=server.store.metadata(batch['game_ids'][1])
    monkeypatch.setattr(server.subprocess,'Popen',lambda *a,**kw:pytest.fail('Cancelled job started a process'))
    server._run_match(cancelled,[])
    assert server.room_service.get_room(rid).status=='playing'
    finish(first['game_id'])
    room=client.get(f'/rooms/{rid}',headers=owner).json()['room']
    assert room['status']=='waiting' and all(s['ready'] for s in room['seats'])
    new=start(client,rid,owner,seed=99)
    assert server.store.metadata(new['game_id'])['room_match_number']==4
    assert len(client.get(f'/rooms/{rid}',headers=owner).json()['room']['batches'])==2


def test_limits_private_history_and_host_permissions(setup):
    client,queue=setup;rid,owner=ready_room(client,True);stranger=account(client)
    for payload in ({'count':0},{'count':11},{'count':1.5},{'count':True},{'seed':1.2},{'seed':2**31-1,'count':2}):
        assert client.post(f'/rooms/{rid}/start-game',headers=owner,json=payload).status_code in (400,422)
    assert not queue.jobs
    batch=start(client,rid,owner,count=2)
    for headers in ({},stranger):
        assert client.get(f'/rooms/{rid}/statistics',headers=headers).status_code==404
        assert client.get(f"/games/{batch['game_id']}/batch",headers=headers).status_code==404
        assert client.post(f"/rooms/{rid}/batches/{batch['batch_id']}/cancel",headers=headers).status_code==404
    public,host=ready_room(client)
    assert client.post(f'/rooms/{public}/start-game',headers=stranger,json={}).status_code==403
    assert client.post(f'/rooms/{public}/start-game',json={}).status_code==401


def test_aggregates_follow_players_across_rotation_and_exclude_missing_scores(setup):
    client,_=setup;rid,owner=ready_room(client)
    batch=start(client,rid,owner,count=3,rotate_seats=True)
    finish(batch['game_ids'][0],winner='P1')
    finish(batch['game_ids'][1],winner='P4')  # Same room owner after rotation.
    finish(batch['game_ids'][2],status='failed',summary=False)
    stats=client.get(f'/rooms/{rid}/statistics',headers=owner).json()
    assert stats['statuses']=={'completed':2,'failed':1}
    assert len(stats['players'])==4
    player=next(p for p in stats['players'] if p['bot_id'].endswith('Batch player-v1'))
    assert player['wins']==2 and player['win_rate']==100
    assert player['averages']['points']==10 and player['totals']['settlements_built']==10
    assert [r['player_id'] for r in player['runs']]==['P1','P4','P3']
    assert player['runs'][2]['points'] is None
    assert client.get(f'/rooms/{rid}/statistics?batch_id=missing',headers=owner).status_code==404
    saved=client.get(f'/rooms/{rid}',headers=owner).json()['room']
    assert len(saved['matches'])==3 and saved['batches'][0]['finished']==3


def test_rematch_preserves_original_rotated_order_and_checks_current_lineup(setup):
    client,_=setup;rid,owner=ready_room(client)
    batch=start(client,rid,owner,count=2,rotate_seats=True)
    for gid in batch['game_ids']: finish(gid)
    old=server.store.metadata(batch['game_ids'][1])
    assert client.get(f"/games/{old['game_id']}/batch",headers=owner).json()['can_rematch']
    rematch=start(client,rid,owner,seed=old['seed'],rematch_of=old['game_id'])
    new=finish(rematch['game_id'])
    assert new['participants']==old['participants'] and new['seed']==old['seed']
    client.post(f'/rooms/{rid}/builtin-bot',headers=owner,json={'seat':1,'difficulty':'hard'})
    name=server.room_service.get_room(rid).seats[0].player_name
    client.post(f'/rooms/{rid}/ready',headers=owner,json={'player_name':name})
    assert client.post(f'/rooms/{rid}/start-game',headers=owner,json={'rematch_of':old['game_id']}).status_code==409


def test_multiplayer_lineup_changes_clear_all_human_readiness(setup):
    client,_=setup
    users=[account(client) for _ in range(4)]
    names=[client.get('/auth/me',headers=h).json()['user']['username'] for h in users]
    room=client.post('/rooms',headers=users[0]).json()['room'];rid=room['room_id']
    for name,headers in zip(names[1:],users[1:]):
        client.post(f'/rooms/{rid}/join',headers=headers,json={'player_name':name})
    for name,headers in zip(names,users):
        bot=client.post('/bots/upload',headers=headers,json={'bot_name':'Multiplayer','bot_version':'v1','bot_code':CODE}).json()
        client.post(f'/rooms/{rid}/attach-bot',headers=headers,json={'player_name':name,'bot_name':bot['bot_id']})
    for name,headers in zip(names,users):client.post(f'/rooms/{rid}/ready',headers=headers,json={'player_name':name})
    bot=client.post('/bots/upload',headers=users[0],json={'bot_name':'Multiplayer','bot_version':'v2','bot_code':CODE}).json()
    client.post(f'/rooms/{rid}/attach-bot',headers=users[0],json={'player_name':names[0],'bot_name':bot['bot_id']})
    assert not any(s.ready for s in server.room_service.get_room(rid).seats)
    for name,headers in zip(names,users):client.post(f'/rooms/{rid}/ready',headers=headers,json={'player_name':name})
    assert client.post(f'/rooms/{rid}/start-game',headers=users[1],json={'count':3}).status_code==403
    batch=start(client,rid,users[0],count=3)
    assert client.post(f"/rooms/{rid}/batches/{batch['batch_id']}/cancel",headers=users[1]).status_code==403
    for gid in batch['game_ids']:finish(gid)
    assert all(s.ready for s in server.room_service.get_room(rid).seats)


def test_restart_recovers_entire_batch_without_losing_its_history(tmp_path):
    store=ReplayStore(tmp_path)
    store.save_batch([{'game_id':f'game-{uuid.uuid4().hex}','status':'queued','batch_id':'batch-test',
                       'batch_index':i,'created_at':str(i)} for i in range(3)])
    queued=store.list_games()[0]
    completed={**queued,'status':'completed','winner':'P2','summary':[{'player_id':'P2','points':10}]}
    # Simulate a stop between writing the replay and updating its catalog row.
    store.finish(queued['game_id'],{'metadata':completed,
        'result':{'status':'completed','winner':'P2','reason':None}},queued)
    store.recover()
    recovered=store.metadata(queued['game_id'])
    assert recovered['winner']=='P2' and recovered['summary']==completed['summary']
    assert [g['status'] for g in store.list_games()]==['completed','failed','failed']
    assert all(g['batch_id']=='batch-test' for g in store.list_games())
    assert len(ReplayStore(tmp_path).list_games())==3


def test_worker_saves_final_piece_counts_and_legacy_stats_keep_public_scores(tmp_path):
    store=ReplayStore(tmp_path)
    metadata={'game_id':f'game-{uuid.uuid4().hex}','status':'queued','seed':20,
        'created_at':'2026-10-12','room_id':'room-stats',
        'participants':[{'player_id':f'P{i}','name':f'Player {i}','bot_id':f'bot-{i}'} for i in range(1,5)]}
    store.save_metadata(metadata)
    run_job({'metadata':metadata,'replay_directory':str(tmp_path),'config':{'max_turns':0},
             'packages':[{'builtin':'easy'}]*4})
    saved=store.metadata(metadata['game_id'])
    for player in saved['summary']:
        assert (player['points'],player['roads'],player['settlements'],player['cities'])==(2,2,2,0)
        assert player['settlements_built']==2 and player['score_visibility']=='final'
    # Same identity using a new version forms a distinct statistics row.
    newer={**saved,'game_id':'game-newer','participants':[dict(p) for p in saved['participants']]}
    newer['participants'][0].update(bot_id='bot-1-v2',bot_version='v2')
    stats=aggregate([newer,saved],store)
    assert len(stats['players'])==5
    old=dict(saved);old.pop('summary')
    stats=aggregate([old],store)
    assert all(p['runs'][0]['score_visibility']=='public' for p in stats['players'])
    assert all(p['averages']['points']==2 for p in stats['players'])


def test_fair_queue_bounds_concurrency_and_shares_capacity_between_batches():
    queue=FairMatchQueue(2)
    release=threading.Event();started=[];lock=threading.Lock();done=threading.Event()
    def job(name):
        with lock: started.append(name)
        if name in ('A0','A1'): assert release.wait(5)
        with lock:
            if len(started)==6:done.set()
    queue.submit_batch(job,[(f'A{i}',) for i in range(4)])
    deadline=time.monotonic()+2
    while len(started)<2 and time.monotonic()<deadline:time.sleep(.01)
    assert started==['A0','A1']
    queue.submit_batch(job,[('B0',),('B1',)])
    release.set();assert done.wait(5)
    # B gets capacity before the first batch drains all its remaining jobs.
    assert started.index('B0') < started.index('A3')
    queue.shutdown()
