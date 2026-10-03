"""Rotate compiled opponents through seats and report measured results."""
import argparse
from collections import Counter
import json
from src.platform.builtin_players import load_player, artifact
from src.simulation import Simulator
from src.simulator.types.identifiers import PlayerId

parser = argparse.ArgumentParser()
parser.add_argument('--seeds', type=int, default=12)
args = parser.parse_args()
wins = Counter()
statuses = Counter()
for seed in range(args.seeds):
    for shift in range(4):
        levels = ['easy', 'medium', 'hard', 'medium']
        levels = levels[shift:] + levels[:shift]
        sim = Simulator(seed=seed)
        sim.register_players({pid: load_player(level) for pid, level in zip(PlayerId.all_players(), levels)})
        sim.run()
        sim.assert_invariants()
        statuses[sim.result['status']] += 1
        if sim.result['winner']:
            wins[levels[int(sim.result['winner'][1:]) - 1]] += 1
print(json.dumps({'artifact': artifact().name, 'matches': args.seeds * 4,
                  'wins': dict(wins), 'statuses': dict(statuses)}, indent=2))
