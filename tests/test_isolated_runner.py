"""Integration checks: run with CATAN_PLAYER_MODE=runner and a real broker."""
import os
from pathlib import Path
import pytest
from src.player.hosted import hosted_player

pytestmark=pytest.mark.skipif(os.getenv('CATAN_PLAYER_MODE')!='runner',reason='Needs the isolated Docker runner')


def test_host_files_network_and_other_player_files_are_inaccessible():
    code='''from src.player import Player
import os, socket
class Probe(Player):
 def choose_action(self,view,options):
  failures=[]
  for path in ('/data/catan.db','/app/src/platform/server.py','/var/run/docker.sock','/run/catan-runner/runner.sock','/proc/1/root/data/catan.db'):
   try:
    with open(path,'rb') as f:f.read(1)
   except OSError: pass
   else: failures.append(path)
  try:
   with open('/sdk/escaped','w') as f:f.write('bad')
  except OSError: pass
  else: failures.append('writable root')
  for host in ('1.1.1.1','169.254.169.254'):
   sock=socket.socket();sock.settimeout(.1)
   try:sock.connect((host,80))
   except OSError:pass
   else:failures.append('network '+host)
   finally:sock.close()
  if os.path.exists('/tmp/other-player-secret'):failures.append('other player file')
  return {'failures':failures,'env_leaked':any(k.startswith('CATAN_') for k in os.environ)}
'''
    writer=hosted_player("from src.player import Player\nclass W(Player):\n def __init__(self):open('/tmp/other-player-secret','w').write('secret')\n def choose_action(self,*args):return {}\n")
    reader=hosted_player(code)
    try:assert reader.choose_action({},[])=={'failures':[],'env_leaked':False}
    finally:reader.close();writer.close()


def test_timeout_and_private_traceback_cross_runner_boundary():
    code="from src.player import Player\nclass P(Player):\n def choose_action(self,*args):raise ValueError('owner-only detail')\n"
    player=hosted_player(code)
    try:
        with pytest.raises(RuntimeError,match='owner-only'):player.choose_action({},[])
        assert 'ValueError' in player.last_error['traceback']
    finally:player.close()
    player=hosted_player("from src.player import Player\nclass P(Player):\n def choose_action(self,*args):\n  while True:pass\n")
    try:
        with pytest.raises(RuntimeError,match='timed out'):player.choose_action({},[])
    finally:player.close()


def test_simulator_implementation_is_not_part_of_player_image():
    with pytest.raises(RuntimeError):
        hosted_player('from src.simulation import Simulator')


def test_excessive_memory_and_oversized_protocol_responses_are_rejected():
    for body,expected in (("return 'x'*3_000_000",'Response too large'),
                          ("return bytearray(1024*1024*1024)",'MemoryError')):
        code='from src.player import Player\nclass P(Player):\n def choose_action(self,*args):'+body+'\n'
        player=hosted_player(code)
        try:
            with pytest.raises(RuntimeError):player.choose_action({},[])
            assert expected in str(player.last_error) or 'memory limit' in str(player.last_error)
        finally:player.close()


def test_player_process_count_is_bounded_and_user_is_unprivileged():
    code='''from src.player import Player
import os, subprocess
class P(Player):
 def choose_action(self,*args):
  children=[];blocked=False
  try:
   for _ in range(10):
    try:children.append(subprocess.Popen(['sleep','10']))
    except OSError:blocked=True;break
   return {'spawned':len(children),'blocked':blocked,'uid':os.getuid()}
  finally:
   for child in children:child.kill()
   for child in children:child.wait()
'''
    player=hosted_player(code)
    try:
        result=player.choose_action({},[])
        assert result['blocked'] and result['spawned']<=7
        assert result['uid']==65534
    finally:player.close()
