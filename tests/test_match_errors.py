import json
import uuid

from fastapi.testclient import TestClient
from src.platform.match_worker import run_job
from src.platform.replay_store import ReplayStore
from tests.test_builtin_rooms import account


def test_hosted_tracebacks_are_private_to_the_failing_owner(tmp_path,monkeypatch):
    from src.platform import server
    monkeypatch.setattr(server,'AUTH_REQUIRED',True)
    store=ReplayStore(tmp_path/'recordings')
    monkeypatch.setattr(server,'store',store)
    client=TestClient(server.app)
    owner,other,stranger=account(client),account(client),account(client)
    uid=lambda headers:client.get('/auth/me',headers=headers).json()['user']['user_id']
    game_id='game-'+uuid.uuid4().hex
    metadata={'game_id':game_id,'seed':20,'created_at':'2026-10-10','status':'queued',
              'private':False,'participants':[{'player_id':'P1','user_id':uid(owner)},
                                              {'player_id':'P2','user_id':uid(other)}]}
    store.save_metadata(metadata)
    code="from src.player import Player\nclass Broken(Player):\n def choose_action(self,view,options):\n  raise ValueError('OWNER_ONLY_SECRET')\n"
    run_job({'metadata':metadata,'replay_directory':str(store.directory),
             'packages':[{'code':code}]+[{'builtin':'easy'}]*3})
    report=store.errors(game_id)['errors']
    assert report[0]['callback']=='choose_action'
    assert 'OWNER_ONLY_SECRET' in report[0]['traceback']
    assert 'ValueError' in report[0]['traceback']
    assert 'OWNER_ONLY_SECRET' not in json.dumps(store.replay(game_id))
    assert 'OWNER_ONLY_SECRET' not in json.dumps(store.metadata(game_id))
    report.append({'player_id':'P2','error':'OTHER_OWNER_SECRET'})
    store.save_errors(game_id,report)
    result=client.get(f'/games/{game_id}/errors',headers=owner)
    assert result.status_code==200 and len(result.json()['errors'])==1
    assert 'OTHER_OWNER_SECRET' not in result.text
    assert client.get(f'/games/{game_id}/errors',headers=other).json()['errors']==[report[1]]
    assert client.get(f'/games/{game_id}/errors',headers=stranger).status_code==403
    assert client.get(f'/games/{game_id}/errors').status_code==401
    assert 'OWNER_ONLY_SECRET' not in client.get(f'/game/{game_id}/replay').text


def test_invalid_action_report_includes_response_phase_and_explanation(tmp_path):
    store=ReplayStore(tmp_path)
    game_id='game-'+uuid.uuid4().hex
    metadata={'game_id':game_id,'seed':20,'created_at':'2026-10-10','status':'queued'}
    store.save_metadata(metadata)
    code="from src.player import Player\nclass Broken(Player):\n def choose_action(self,view,options):\n  return next((a for a in options if a.type=='TRADE'),options[0])\n"
    run_job({'metadata':metadata,'replay_directory':str(tmp_path),
             'packages':[{'code':code}]+[{'builtin':'easy'}]*3})
    error=store.errors(game_id)['errors'][0]
    assert error['returned_action']=={'type':'TRADE'}
    assert error['phase']=='PLAYING' and error['callback']=='validate_action'
    assert all(field in error['error'] for field in ('give','receive','recipients'))
    assert 'TRADE' in error['available_types']
    assert store.replay(game_id)['result']['status']=='failed'
