import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from src.simulator.cli import main


@pytest.mark.parametrize('debug',[False,True])
def test_trade_template_failure_explains_fields_and_streams_prints(tmp_path,capsys,debug):
    path=tmp_path/'bad_trade.py'
    path.write_text('''from src.player import Player
class TestPlayer(Player):
    def choose_action(self,view,options):
        print("player decision", flush=True)
        return next((a for a in options if a.type == 'TRADE'), options[0])
''')
    args=['play','--player',str(path),'--opponents','easy','--seed','20','--output','json']
    if debug: args.append('--debug')
    assert main(args)==1
    out=capsys.readouterr()
    result=json.loads(out.out)
    assert 'player decision' in out.err
    assert all(field in result['reason'] for field in ('give','receive','recipients','templates'))
    context=result['failure_context']
    assert context['phase']=='PLAYING' and context['returned_action']=={'type':'TRADE'}
    assert context['decision_id']>=16


@pytest.mark.parametrize('debug',[False,True])
def test_callback_traceback_uses_original_file_and_json_is_clean(tmp_path,capsys,debug):
    path=tmp_path/'broken.py'
    path.write_text('''from src.player import Player
class TestPlayer(Player):
    def choose_action(self,view,options):
        print('before exception')
        raise ValueError('my diagnostic message')
''')
    args=['play','--player',str(path),'--output','json']
    if debug:args.append('--debug')
    assert main(args)==1
    out=capsys.readouterr()
    result=json.loads(out.out)
    assert 'before exception' in out.err
    assert str(path) in result['failure_context']['traceback']
    assert 'my diagnostic message' in result['failure_context']['traceback']


def test_debug_mode_actually_stops_at_breakpoint(tmp_path):
    path=tmp_path/'paused.py'
    path.write_text('''from src.player import Player
class TestPlayer(Player):
    def on_game_start(self,view):
        breakpoint()
    def choose_action(self,view,options):
        return options[0]
''')
    env=dict(os.environ)
    env.pop('PYTHONBREAKPOINT',None)
    result=subprocess.run([sys.executable,'-m','src.simulator.cli','play','--player',str(path),
                           '--debug','--max-turns','0','--output','json'],
                          input='continue\n',capture_output=True,text=True,env=env,timeout=20)
    assert result.returncode==0,result.stderr
    assert '(Pdb)' in result.stderr
    assert json.loads(result.stdout)['status']=='stopped'


def test_summary_traceback_is_readable_and_quiet_suppresses_both_streams(tmp_path,capsys):
    path=tmp_path/'noisy.py'
    path.write_text('''import sys
from src.player import Player
class TestPlayer(Player):
    def choose_action(self,view,options):
        print('hidden stdout')
        print('hidden stderr',file=sys.stderr)
        raise ValueError('explain this failure')
''')
    assert main(['play','--player',str(path),'--debug','--quiet-player'])==1
    out=capsys.readouterr()
    assert 'hidden stdout\n' not in out.err and 'hidden stderr\n' not in out.err
    assert '\nTraceback (most recent call last):\n' in out.err
    assert 'ValueError: explain this failure\n' in out.err


def test_update_refuses_dirty_checkout_and_uses_ff_only(tmp_path,monkeypatch,capsys):
    from src.simulator import update
    root=tmp_path/'checkout'
    (root/'.git').mkdir(parents=True)
    (root/'pyproject.toml').touch()
    monkeypatch.setattr(update,'__file__',str(root/'src/simulator/update.py'))
    calls=[]
    monkeypatch.setattr(update.subprocess,'check_output',lambda *a,**k:' M my_player.py')
    monkeypatch.setattr(update.subprocess,'run',lambda cmd,**k:calls.append(cmd))
    with pytest.raises(RuntimeError,match='local changes'):update.update_installation()
    assert not calls
    monkeypatch.setattr(update.subprocess,'check_output',lambda *a,**k:'')
    assert main(['--update'])==0
    assert ['git','pull','--ff-only'] in calls
    assert all('reset' not in c for c in calls)
    assert [sys.executable,'-m','pip','install','-e',str(root)] in calls


def test_installed_copy_update_uses_official_repository(tmp_path,monkeypatch):
    from src.simulator import update
    monkeypatch.setattr(update,'__file__',str(tmp_path/'src/simulator/update.py'))
    calls=[]
    monkeypatch.setattr(update.subprocess,'run',lambda cmd,**k:calls.append(cmd))
    assert update.update_installation()==0
    assert calls==[[sys.executable,'-m','pip','install','--upgrade','--force-reinstall',f'git+{update.REPOSITORY}']]


def test_player_host_is_not_shadowed_by_sdk_in_bot_project(tmp_path,monkeypatch,capsys):
    import shutil
    sdk=tmp_path/'src/player'
    sdk.mkdir(parents=True)
    (tmp_path/'src/__init__.py').write_text('')
    for name in ('__init__.py','interface.py','types.py'):
        shutil.copy(Path('src/player')/name,sdk/name)
    source=Path('examples/my_player.py').read_text()
    path=tmp_path/'my_player.py'
    path.write_text(source)
    monkeypatch.chdir(tmp_path)
    assert main(['play','--player',str(path),'--max-turns','0','--output','json'])==0
    result=json.loads(capsys.readouterr().out)
    assert result['status']=='stopped' and result['decisions']==16
