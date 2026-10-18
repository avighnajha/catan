"""Hosted player transport. Production fails closed without the runner socket."""
import http.client
import json
import os
import socket
from .interface import Player, thaw


class RunnerConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout=20):
        super().__init__('runner', timeout=timeout)
        self.path=path

    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


class HostedPlayer(Player):
    def __init__(self, code):
        self.path=os.environ['CATAN_RUNNER_SOCKET']
        self.last_error=None
        self.session=None
        self.session=self._request('/start',{'code':code})['session']

    def _request(self, path, payload):
        connection=RunnerConnection(self.path)
        try:
            connection.request('POST',path,json.dumps(payload,allow_nan=False),{'Content-Type':'application/json'})
            response=connection.getresponse()
            raw=response.read(2_100_001)
            if len(raw)>2_100_000: raise RuntimeError('Runner response exceeds limit')
            result=json.loads(raw)
            if response.status!=200:
                self.last_error=result
                error=RuntimeError(result.get('detail','Isolated player execution failed'))
                error.player_diagnostics=result.get('traceback','')
                raise error
            return result
        except (OSError,http.client.HTTPException) as cause:
            raise RuntimeError('Isolated runner unavailable; unrestricted execution is disabled') from cause
        finally:
            connection.close()

    def _call(self, method, *args):
        return self._request('/call',{'session':self.session,'method':method,'args':thaw(args)})['result']

    def on_game_start(self,view): self._call('on_game_start',view)
    def on_event(self,event): self._call('on_event',event)
    def choose_action(self,view,options): return self._call('choose_action',view,options)
    def on_game_end(self,result): self._call('on_game_end',result)
    def close(self):
        if self.session:
            session,self.session=self.session,None
            try:self._request('/close',{'session':session})
            except RuntimeError:pass # Broker TTL reaps a disconnected client's container.


def hosted_player(code):
    mode=os.getenv('CATAN_PLAYER_MODE','local')
    if mode=='runner': return HostedPlayer(code)
    if mode!='local' or os.getenv('CATAN_AUTH_REQUIRED','0').lower() not in ('0','false','no'):
        raise RuntimeError('Hosted uploads require CATAN_PLAYER_MODE=runner and an isolated runner')
    from .process import ProcessPlayer
    return ProcessPlayer(code,capture_errors=True)
