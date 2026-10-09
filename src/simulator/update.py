"""Explicit update command. Never resets or discards a user's checkout."""
from pathlib import Path
import subprocess
import sys

REPOSITORY='https://github.com/avighnajha/catan.git'


def update_installation():
    root=Path(__file__).resolve().parents[2]
    if (root/'.git').exists() and (root/'pyproject.toml').exists():
        dirty=subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True)
        if dirty.strip():
            raise RuntimeError(f'Cannot update: {root} has local changes. Commit or stash them, then rerun catansim update. Nothing was changed.')
        subprocess.run(['git','rev-parse','--abbrev-ref','--symbolic-full-name','@{u}'],cwd=root,check=True,capture_output=True)
        subprocess.run(['git','pull','--ff-only'],cwd=root,check=True)
        subprocess.run([sys.executable,'-m','pip','install','-e',str(root)],check=True)
    else:
        subprocess.run([sys.executable,'-m','pip','install','--upgrade','--force-reinstall',
                        f'git+{REPOSITORY}'],check=True)
    print('Updated catansimulator. Restart any running Python/IDE sessions to use the new code.')
    return 0
