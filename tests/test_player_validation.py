from pathlib import Path
import json
import threading
import time
import uuid
import pytest
from fastapi.testclient import TestClient
from src.platform.player_validation import validate, scenario, SCENARIOS
from src.player.example import ExamplePlayer
from src.player.hosted import hosted_player

STARTER=Path('examples/my_player.py').read_text(encoding='utf-8')


class LocalExample(ExamplePlayer):
    def close(self): pass


@pytest.mark.parametrize('name',SCENARIOS)
def test_scenarios_are_valid_engine_states(name):
    scenario('',name,lambda code:LocalExample())


def test_three_stages_run_real_games_with_different_seeds_and_seats():
    reports=[]
    assert validate('',lambda *args,**extra:reports.append((args,extra)),lambda code:LocalExample())
    passed=[args[0] for args,_ in reports if args[1]=='passed']
    assert passed==['quick','scenarios','games']
    games=reports[-1][1]['games']
    assert len({g['seed'] for g in games})==3
    assert len({g['seat'] for g in games})==3
    assert all(g['status'] in ('completed','stopped') for g in games)


def test_invalid_discard_is_explained_in_scenario_with_own_view_only():
    class Broken(LocalExample):
        def choose_action(self,view,options):
            if options[0].type=='DISCARD':return options[0]
            return super().choose_action(view,options)
    reports=[]
    assert not validate('',lambda *args,**extra:reports.append((args,extra)),lambda code:Broken())
    args,extra=reports[-1]
    assert args[:2]==('scenarios','failed')
    error=extra['details']
    assert error['scenario']=='Discard after seven'
    assert error['returned_action']['type']=='DISCARD'
    assert 'omit count' in error['hint']
    assert error['available_actions'][0]['type']=='DISCARD'
    assert all('resources' not in other for other in error['player_view']['opponents'])


def test_event_exception_contains_callback_and_private_traceback():
    class Broken(LocalExample):
        def on_event(self,event):raise ValueError('private validation error')
    reports=[]
    assert not validate('',lambda *args,**extra:reports.append((args,extra)),lambda code:Broken())
    failure=reports[-1][1]['details']
    assert failure['callback']=='on_event'
    assert 'private validation error' in failure['traceback']


def test_production_never_falls_back_to_local_execution(monkeypatch):
    monkeypatch.setenv('CATAN_AUTH_REQUIRED','1')
    monkeypatch.setenv('CATAN_PLAYER_MODE','local')
    with pytest.raises(RuntimeError,match='require'): hosted_player(STARTER)


def test_runner_command_has_no_host_mounts_network_or_secrets():
    from src.player.runner import container_command
    command=container_command('test')
    assert command[command.index('--network')+1]=='none'
    assert '--read-only' in command and '--cap-drop' in command
    assert command[command.index('--user')+1]=='65534:65534'
    assert command[command.index('--pids-limit')+1]=='8'
    assert all(flag not in command for flag in ('-v','--volume','--mount','--privileged','--pid','--ipc'))
    assert '/var/run/docker.sock' not in ' '.join(command)


def test_upload_validation_is_private_and_does_not_create_history(monkeypatch):
    from src.platform import server
    from tests.test_builtin_rooms import account
    client=TestClient(server.app)
    monkeypatch.setattr(server,'AUTH_REQUIRED',True)
    owner,other=account(client),account(client)
    headers=owner
    before_games=client.get('/games',headers=headers).json()
    before_stats=client.get('/account/stats',headers=headers).json()
    name='Validation'+uuid.uuid4().hex[:8]
    response=client.post('/bots/upload?wait=false',headers=headers,json={
        'bot_name':name,'bot_version':'v1','bot_code':STARTER})
    assert response.status_code==200,response.text
    report=response.json();url='/bots/validations/'+report['validation_id']
    assert client.get(url,headers=other).status_code==404
    assert client.get(url).status_code==401
    deadline=time.monotonic()+180
    while report['status'] in ('queued','running') and time.monotonic()<deadline:
        time.sleep(.2);report=client.get(url,headers=headers).json()
    assert report['status']=='passed',report
    assert report['validated'] and report['bot_id']
    assert all(s['status']=='passed' for s in report['stages'].values())
    assert len(report['stages']['games']['games'])==3
    assert client.get('/games',headers=headers).json()==before_games
    after=client.get('/account/stats',headers=headers).json()
    assert after['games_played']==before_stats['games_played']
    assert after['wins']==before_stats['wins']


def test_failed_upload_can_retry_same_name_and_version(monkeypatch):
    from src.platform import server
    from tests.test_builtin_rooms import account
    client=TestClient(server.app);owner=account(client)
    name='Retry'+uuid.uuid4().hex[:8]
    payload={'bot_name':name,'bot_version':'v1','bot_code':'not valid python!'}
    for _ in range(2):
        report=client.post('/bots/upload',headers=owner,json=payload).json()
        assert report['status']=='failed' and not report['validated']
        assert report['stages']['quick']['status']=='failed'
        assert 'SyntaxError' in report['stages']['quick']['details']['traceback']
        assert report['stages']['scenarios']['status']=='skipped'
    assert name not in [b['name'] for b in client.get('/bots',headers=owner).json()['bots']]


def test_queue_limits_and_restart_recovery(tmp_path):
    from src.platform.validation_jobs import ValidationJobs
    gate=threading.Event()
    jobs=ValidationJobs(str(tmp_path/'reports.db'),lambda data,owner:None)
    def block(*args):gate.wait(5)
    jobs.execute=block
    try:
        report=jobs.submit({},'owner')
        with pytest.raises(ValueError,match='already'):jobs.submit({},'owner')
        with pytest.raises(KeyError):jobs.get(report['validation_id'],'other')
    finally:
        gate.set();jobs.pool.shutdown()
    recovered=ValidationJobs(jobs.database,lambda *a:None)
    assert recovered.get(report['validation_id'],'owner')['status']=='failed'
    recovered.pool.shutdown()


def test_report_publishing_retries_a_windows_reader_lock(tmp_path,monkeypatch):
    from src.platform import validation_worker
    original=validation_worker.os.replace;calls=[]
    def replace(source,destination):
        calls.append(source)
        if len(calls)==1:raise PermissionError('reader has the report open')
        original(source,destination)
    monkeypatch.setattr(validation_worker.os,'replace',replace)
    path=tmp_path/'report.json'
    validation_worker.publish(path,{'status':'passed'})
    assert json.loads(path.read_text())=={'status':'passed'}
    assert len(calls)==2
