# Built-in practice players

Easy, Medium, and Hard implement the same `src.player.Player` contract as uploads.
They run on the backend, receive only their own exact hand, and use public events
to keep their own memory. They never receive a raw simulator state.

The checked-in `.pyc` files are compiled Python bytecode. They provide a modest
barrier to reading the implementation, not cryptographic secrecy. No strategy
source is tracked. Python 3.10 is included for local development; Python 3.12 is
included for the ARM64 production Docker runtime. Bytecode is independent of CPU
architecture but specific to the Python minor version. Unsupported versions fail
explicitly rather than substituting another strategy.

Versions and artifact SHA-256 hashes are recorded with each match. Existing
recordings remain self-contained when an opponent version changes.

Rebuild from your retained private source with:

```sh
python scripts/compile-opponents.py /path/to/private/players.py
PYTHONPATH=. python scripts/benchmark-opponents.py --seeds 8
```

Run the compiler under every supported Python minor version. The private module
must define `EasyPlayer`, `MediumPlayer`, and `HardPlayer`. Keep its source outside
Git; `.private-opponents/` is ignored by Git and Docker for local build inputs.
Commit the resulting artifacts only after testing and comparing source versus
compiled behavior. Bump the public version when changing strategies.

Initial benchmark: 32 games, seeds 0–7, four seat rotations; one Easy, two Medium,
and one Hard per game. All games completed. Easy won 0/32 appearances; Medium won
20/64 appearances (31.25%); Hard won 12/32 appearances (37.5%). These are initial
practice levels, not a claim of optimal Catan play.
