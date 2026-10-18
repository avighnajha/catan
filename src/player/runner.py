"""Trusted Unix-socket broker. Only this service can control Docker.

All container arguments are server-owned constants. Submitted code travels over
stdin; no client-selected command, path, image, mount or environment is accepted.
"""
import http.server
import json
import os
from pathlib import Path
import socketserver
import subprocess
import threading
import time
import uuid
from .process import ProcessPlayer

IMAGE=os.getenv('CATAN_PLAYER_IMAGE','catan-player:local')
PREFIX='catan-player-'
LABEL='io.catansimulator.runner='+os.getenv('CATAN_RUNNER_ID','main')


def container_command(name):
    return ['docker','run','-i','--name',name,'--label',LABEL,
        '--network','none','--read-only','--user','65534:65534',
        '--cap-drop','ALL','--security-opt','no-new-privileges:true',
        '--pids-limit','8','--memory','256m','--memory-swap','256m','--cpus','0.5',
        '--ulimit','nofile=64:64','--ulimit','fsize=1048576:1048576',
        '--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777',
        '--log-driver','none','--env','PYTHONDONTWRITEBYTECODE=1',
        '--env','PYTHONUNBUFFERED=1',IMAGE]


def remove_container(name):
    subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL,timeout=10)


def start_player(code):
    name=PREFIX+uuid.uuid4().hex
    try:
        player=ProcessPlayer(code,capture_errors=True,_command=container_command(name),
            _initial_input=(json.dumps({'code':code})+'\n').encode(),
            _startup_timeout=15)
        player.container_name=name
        player._cleanup=lambda:remove_container(name)
        return player
    except Exception:
        remove_container(name);raise


def container_failure(player):
    if player.process.poll() is None:return None
    result=subprocess.run(['docker','inspect','--format','{{json .State}}',player.container_name],
                          capture_output=True,text=True,timeout=5)
    if result.returncode:return None
    state=json.loads(result.stdout)
    if state.get('OOMKilled'):return 'Player exceeded its 256 MB memory limit'
    if state.get('ExitCode') in (152,):return 'Player exceeded its 30-second CPU budget'
    if state.get('ExitCode'):return f"Player process exited (code {state['ExitCode']})"
    return None


PROBE_CODE='''from src.player import Player
import os, socket
class IsolationProbe(Player):
    def __init__(self):
        for path in ('/data/catan.db', '/app/src/platform/server.py', '/var/run/docker.sock', '/run/catan-runner/runner.sock'):
            try:
                with open(path, 'rb') as stream: stream.read(1)
            except OSError: pass
            else: raise RuntimeError('Forbidden host path accessible: '+path)
        try:
            with open('/sdk/isolation-probe', 'w') as stream: stream.write('test')
        except OSError: pass
        else: raise RuntimeError('Player root filesystem is writable')
        with open('/tmp/private-probe', 'w') as stream: stream.write('private')
        for address in ('1.1.1.1', '169.254.169.254'):
            connection=socket.socket(); connection.settimeout(.2)
            try: connection.connect((address, 80))
            except OSError: pass
            else: raise RuntimeError('External network accessible')
            finally: connection.close()
        if any(k.startswith('CATAN_') for k in os.environ): raise RuntimeError('Server environment leaked')
    def choose_action(self,view,options): return options[0]
'''


def verify_isolation():
    player=start_player(PROBE_CODE)
    try:
        if player.choose_action({},[{'type':'REJECT'}])!={'type':'REJECT'}:
            raise RuntimeError('Isolation probe failed')
    finally: player.close()


class Broker:
    def __init__(self):
        self.sessions={}
        self.lock=threading.Lock()
        self.capacity=threading.BoundedSemaphore(12)

    def close(self, sid):
        with self.lock: entry=self.sessions.pop(sid,None)
        if entry:
            try:
                with entry['lock']: entry['player'].close()
            finally: self.capacity.release()

    def request(self, path, data):
        if path=='/start':
            if set(data)!={'code'} or not isinstance(data['code'],str) or len(data['code'])>200_000:
                raise ValueError('Supply one Python source file, at most 200 KB')
            if not self.capacity.acquire(blocking=False): raise RuntimeError('Runner capacity reached; retry shortly')
            try: player=start_player(data['code'])
            except BaseException:
                self.capacity.release();raise
            sid=uuid.uuid4().hex
            with self.lock:
                self.sessions[sid]={'player':player,'lock':threading.Lock(),'created':time.monotonic(),'used':time.monotonic()}
            return {'session':sid}
        if path=='/close': self.close(data['session']);return {'closed':True}
        if path!='/call': raise ValueError('Unknown runner operation')
        method=data['method'];args=data['args']
        counts={'on_game_start':1,'on_event':1,'choose_action':2,'on_game_end':1}
        if method not in counts or not isinstance(args,list) or len(args)!=counts[method]:
            raise ValueError('Unknown callback or incorrect argument count')
        with self.lock: entry=self.sessions.get(data['session'])
        if not entry: raise ValueError('Player session expired')
        with entry['lock']:
            entry['used']=time.monotonic()
            try: return {'result':getattr(entry['player'],method)(*args)}
            except Exception as error:
                detail=entry['player'].last_error or {}
                error.player_diagnostics=detail.get('traceback') or entry['player'].diagnostics.decode('utf-8',errors='replace')
                explanation=container_failure(entry['player']) or detail.get('detail') or detail.get('error')
                if explanation:error.args=(explanation,)
                raise

    def reap(self):
        while True:
            time.sleep(10)
            with self.lock:
                stale=[sid for sid,e in self.sessions.items()
                       if time.monotonic()-e['used']>45 or time.monotonic()-e['created']>240]
            for sid in stale:
                try: self.close(sid)
                except Exception: pass


broker=Broker()


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        status=200
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=2_100_000: raise ValueError('Invalid request length')
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict): raise ValueError('Expected an object')
            result=broker.request(self.path,data)
        except Exception as error:
            status=400
            result={'error':type(error).__name__,'detail':str(error)[:8192],
                    'traceback':getattr(error,'player_diagnostics','')[-16384:]}
        encoded=json.dumps(result,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(encoded)));self.end_headers()
        self.wfile.write(encoded)

    def log_message(self,*args): pass


class Server(socketserver.ThreadingMixIn,getattr(socketserver,'UnixStreamServer',socketserver.TCPServer)):
    daemon_threads=True
    def get_request(self):
        sock,address=super().get_request();sock.settimeout(25);return sock,address


def main():
    # Remove orphaned containers from an interrupted broker before accepting jobs.
    result=subprocess.run(['docker','ps','-aq','--filter','label='+LABEL],capture_output=True,text=True,check=True,timeout=15)
    for cid in result.stdout.split(): remove_container(cid)
    path=Path(os.getenv('CATAN_RUNNER_SOCKET','/run/catan-runner/runner.sock'))
    path.parent.mkdir(parents=True,exist_ok=True);path.unlink(missing_ok=True)
    verify_isolation() # No submissions execute if the runtime protection check fails.
    threading.Thread(target=broker.reap,daemon=True).start()
    with Server(str(path),Handler) as server:
        os.chmod(path,0o666) # Private named volume: mounted only in broker and API.
        server.serve_forever()


if __name__=='__main__': main()
