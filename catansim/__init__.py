"""Public local simulator API. Install the full catansimulator distribution."""
from pathlib import Path

import src as _src

# The standalone SDK also contains src/__init__.py. Allow that interface-only
# package to find the installed engine without replacing its Player classes or
# inserting directories into the caller's sys.path.
_engine = str(Path(__file__).resolve().parent.parent / 'src')
if _engine not in _src.__path__:
    _src.__path__.append(_engine)

from src.player import Player, freeze, thaw
import src.player as _player

_player_engine = str(Path(_engine) / 'player')
if _player_engine not in _player.__path__:
    _player.__path__.append(_player_engine)

from src.simulation.environment import CatanEnv

__all__ = ['CatanEnv', 'Player', 'freeze', 'thaw']
