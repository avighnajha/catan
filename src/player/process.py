"""Persistent local process adapter with bounded protocol and callback time.

This isolates execution/lifetime, not hostile OS access. Hosted untrusted code
requires an OS sandbox; the web application remains a trusted local tool.
"""
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import codecs
from .interface import Player, thaw

MAX_MESSAGE=2_000_000


def validate_player(code):
    """Import, instantiate and exercise lifecycle, events and one real choice."""
    from ..simulation import Simulator
    from ..simulator.types.identifiers import PlayerId
    from .example import ExamplePlayer
    player=ProcessPlayer(code)
    try:
        sim=Simulator(0)
        sim.register_players({pid:player if pid==PlayerId.P1 else ExamplePlayer() for pid in PlayerId.all_players()})
        sim.step()
        if sim.result is not None: raise ValueError('Player failed its initial decision smoke test')
        player.on_game_end({'status':'validation','winner':None})
    finally:
        player.close()


def terminate_tree(process):
    if os.name=='nt':
        if process.poll() is None:
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW,timeout=10)
    else:
        try: os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError: pass
    try: process.wait(timeout=5)
    except subprocess.TimeoutExpired: process.kill()


class ProcessPlayer(Player):
    def __init__(self,code,timeout=2.0,trusted_local=False,log_stream=None,source_path=None,capture_errors=False):
        self.timeout=timeout
        self.trusted_local=trusted_local
        self.log_stream=log_stream
        self.last_error=None
        self.closed=False
        self.job=None
        self.temp=tempfile.TemporaryDirectory(prefix='catan_player_')
        source=Path(self.temp.name)/'implementation.py'
        source.write_text(code,encoding='utf-8')
        if source_path is not None:
            if not trusted_local: raise ValueError('source_path is for trusted local execution only')
            source=Path(source_path).resolve()
        self.messages=queue.Queue(maxsize=2)
        self.counter=0
        env={k:v for k,v in os.environ.items() if k in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP','LANG')}
        env['PYTHONPATH']=str(Path(__file__).resolve().parents[2])
        if trusted_local: env['PYTHONPATH']+=os.pathsep+str(source.parent)
        env['PYTHONIOENCODING']='utf-8'
        # With -m, the working directory precedes PYTHONPATH. An extracted SDK
        # can therefore shadow the installed simulator's src.player package.
        # Pin our own package first while preserving the user's working directory.
        bootstrap="import sys, runpy; sys.path.insert(0, sys.argv.pop(1)); runpy.run_module('src.player.host', run_name='__main__', alter_sys=True)"
        command=[sys.executable,'-u','-c',bootstrap,str(Path(__file__).resolve().parents[2]),str(source)]
        if trusted_local: command.append('--trusted-local')
        if capture_errors: command.append('--capture-errors')
        self.process=subprocess.Popen(command,
            cwd=None if trusted_local else self.temp.name,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            creationflags=(subprocess.CREATE_NO_WINDOW | (0 if trusted_local else 0x4)) if os.name=='nt' else 0,
            start_new_session=os.name!='nt')
        if os.name=='nt' and not trusted_local:
            try:
                from .windows_job import WindowsJob
                self.job=WindowsJob(self.process)
            except Exception:
                self.process.kill();self.process.wait();self.temp.cleanup();raise
        self.diagnostics=bytearray()
        threading.Thread(target=self._read,daemon=True).start()
        self.error_thread=threading.Thread(target=self._drain_errors,daemon=True)
        self.error_thread.start()
        try:
            hello=self._receive()
            if hello!={'ready':True,'protocol_version':1}: raise RuntimeError('Player handshake failed')
        except Exception as error:
            self.close()
            if capture_errors: error.player_diagnostics=self.diagnostics.decode('utf-8',errors='replace')
            raise

    def _read(self):
        try:
            while True:
                line=self.process.stdout.readline(MAX_MESSAGE+1)
                if not line: raise RuntimeError('Player process exited')
                if len(line)>MAX_MESSAGE: raise RuntimeError('Response exceeds limit')
                item=json.loads(line)
                self.messages.put_nowait(item)
        except Exception:
            try: self.messages.put_nowait({'error':'Invalid player protocol or process exit'})
            except queue.Full: pass

    def _drain_errors(self):
        decoder=codecs.getincrementaldecoder('utf-8')(errors='replace')
        while True:
            try: data=self.process.stderr.read1(4096)
            except (ValueError,OSError): return
            if not data: return
            room=max(0,16384-len(self.diagnostics))
            self.diagnostics.extend(data[:room])
            if self.log_stream is not None:
                try:
                    self.log_stream.write(decoder.decode(data));self.log_stream.flush()
                except (OSError,ValueError): pass

    def _receive(self):
        try: item=self.messages.get(timeout=self.timeout)
        except queue.Empty:
            self.close();raise TimeoutError('Player callback timed out')
        if not isinstance(item,dict) or 'error' in item:
            if isinstance(item,dict): self.last_error=item
            detail=(item.get('traceback') or item.get('detail') or item.get('error')) if isinstance(item,dict) else ''
            raise RuntimeError(f'Player callback failed: {detail}' if self.trusted_local else 'Player callback failed')
        return item

    def _request(self,method,*args):
        self.counter+=1
        data=json.dumps({'id':self.counter,'method':method,'args':thaw(args)},allow_nan=False).encode()+b'\n'
        if len(data)>MAX_MESSAGE: raise ValueError('Request too large')
        # A stuck reader must not block the supervisor on a full input pipe.
        completed=threading.Event();errors=[]
        def write():
            try: self.process.stdin.write(data);self.process.stdin.flush()
            except Exception as error: errors.append(error)
            finally: completed.set()
        threading.Thread(target=write,daemon=True).start()
        if not completed.wait(self.timeout): self.close();raise TimeoutError('Player input stalled')
        if errors: raise RuntimeError('Player process closed')
        response=self._receive()
        if response.get('id')!=self.counter or 'result' not in response: raise RuntimeError('Mismatched response')
        return response['result']

    def on_game_start(self,view): self._request('on_game_start',view)
    def on_event(self,event): self._request('on_event',event)
    def choose_action(self,view,options): return self._request('choose_action',view,options)
    def on_game_end(self,result): self._request('on_game_end',result)

    def close(self):
        if self.closed: return
        self.closed=True
        if self.job: self.job.close()
        terminate_tree(self.process)
        self.error_thread.join(timeout=1)
        for pipe in (self.process.stdin,self.process.stdout,self.process.stderr):
            try: pipe.close()
            except OSError: pass
        self.temp.cleanup()
