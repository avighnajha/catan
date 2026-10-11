"""Inspect setup, one decision, one turn and the rest of the current round."""
from catansim import CatanEnv
from my_player import MyPlayer


def main():
    env = CatanEnv(player_factory=MyPlayer, opponents='easy', max_turns=8)
    env.reset(seed=20)
    view, info = env.run_setup()
    print('Setup:', info.phase, 'decision', info.decision_id)
    view, info = env.run_step()
    print('One decision:', info.phase, 'next seat', info.acting_player)
    view, info = env.run_turn()
    print('Turn finished:', info.turn_number, 'next seat', info.acting_player)
    view, info = env.run_round()
    print('Round finished:', info.round_number, 'next seat', info.acting_player)
    print('Your hand:', dict(view.self.resources))
    print('Remaining game:', dict(env.run()))


if __name__ == '__main__': main()
