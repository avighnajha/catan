"""Versioned built-in players, loaded from checked-in compiled artifacts."""
import hashlib
import importlib.util
from importlib.machinery import SourcelessFileLoader
from pathlib import Path
import sys

LEVELS = ('easy', 'medium', 'hard')
VERSION = 'v1'


def artifact():
    path = Path(__file__).with_name('opponents') / f'players-{sys.implementation.cache_tag}.pyc'
    if not path.exists():
        raise RuntimeError(f'Built-in opponents are unavailable for {sys.implementation.cache_tag}')
    return path


def load_player(level):
    if level not in LEVELS:
        raise ValueError('Choose easy, medium, or hard')
    loader = SourcelessFileLoader('catan_builtin_players', str(artifact()))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return getattr(module, level.title() + 'Player')()


def catalog():
    return [{'bot_id': f'builtin-{level}-{VERSION}', 'name': f'{level.title()} bot',
             'version': VERSION, 'difficulty': level, 'validated': True, 'builtin': True}
            for level in LEVELS]


def package(bot_id):
    from .bot_registry import BotPackage
    item = next((item for item in catalog() if item['bot_id'] == bot_id), None)
    if item is None:
        return None
    result = BotPackage(bot_id=bot_id, name=item['name'], version=VERSION, validated=True)
    result.metadata = {'builtin': item['difficulty'], 'sha256': hashlib.sha256(artifact().read_bytes()).hexdigest()}
    return result
