"""Run the starter against built-in opponents; replace the MyPlayer import."""
import argparse
from collections import Counter
import json

from catansim import CatanEnv, thaw
from my_player import MyPlayer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--games', type=int, default=100)
    parser.add_argument('--seed', type=int, default=20)
    parser.add_argument('--opponents', choices=['easy', 'medium', 'hard'], default='easy')
    parser.add_argument('--max-turns', type=int, default=1000)
    args = parser.parse_args()
    if args.games < 1: parser.error('--games must be positive')
    runs = []
    for index in range(args.games):
        seat = f'P{index % 4 + 1}'
        seed = args.seed + index // 4
        env = CatanEnv(player_factory=MyPlayer, player_id=seat,
                       opponents=args.opponents, max_turns=args.max_turns)
        env.reset(seed=seed)
        result = thaw(env.run())
        runs.append(dict(result, seed=seed, player_id=seat,
                         score=env.sim.build_view_for_player(env.player_id).self.victory_points))
    completed = [r for r in runs if r['status'] == 'completed']
    print(json.dumps({'games': len(runs), 'statuses': dict(Counter(r['status'] for r in runs)),
                      'wins': sum(r['winner'] == r['player_id'] for r in completed),
                      'completed_games': len(completed), 'runs': runs}, indent=2))


if __name__ == '__main__': main()
