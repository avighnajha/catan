"""Trusted local loading and decision diagnostics for the development CLI."""
import contextlib
import importlib.util
import inspect
from pathlib import Path
import sys
import traceback

from ..player import Player, thaw


def load_local_player(path, stream):
    path=Path(path).resolve()
    sys.path.insert(0,str(path.parent))
    spec=importlib.util.spec_from_file_location('catan_local_player',path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        spec.loader.exec_module(module)
        classes=[c for c in vars(module).values() if inspect.isclass(c) and c is not Player
                 and issubclass(c,Player) and c.__module__==module.__name__]
        if len(classes)!=1: raise ValueError('Define exactly one Player subclass')
        if classes[0].choose_action is Player.choose_action: raise ValueError('Override choose_action')
        return classes[0]()


class DiagnosticPlayer(Player):
    def __init__(self, player, stream):
        self.player=player
        self.stream=stream
        self.context=None
        self.failure=None
        self.protocol_version=player.protocol_version

    def call(self, method, *args):
        try:
            with contextlib.redirect_stdout(self.stream), contextlib.redirect_stderr(self.stream):
                return getattr(self.player,method)(*args)
        except Exception:
            self.failure={'callback':method,'traceback':traceback.format_exc()}
            raise

    def on_game_start(self,view): self.call('on_game_start',view)
    def on_event(self,event): self.call('on_event',event)
    def on_game_end(self,result): self.call('on_game_end',result)

    def choose_action(self,view,options):
        self.context={'player_id':view.player_id,'decision_id':view.decision_id,
                      'phase':view.turn.phase,
                      'available_types':sorted({a['type'] for a in options})}
        action=self.call('choose_action',view,options)
        self.context['returned_action']=thaw(action)
        return action
