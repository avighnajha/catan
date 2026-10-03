"""Compile an external strategy source; no source is embedded in the repository."""
import argparse
import py_compile
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('source', type=Path)
parser.add_argument('--output', type=Path, default=Path('src/platform/opponents'))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
py_compile.compile(str(args.source), cfile=str(args.output / f'players-{sys.implementation.cache_tag}.pyc'),
                   dfile='builtin-opponents', doraise=True,
                   invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
