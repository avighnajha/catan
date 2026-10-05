"""Runnable interface demonstration. Add your own decision logic here."""
from collections.abc import Sequence
from src.player import Player, PlayerView, PlayerEvent, GameResult, Action, ActionOption, Resource


class MyPlayer(Player):
    def on_game_start(self, view: PlayerView) -> None:
        # One instance persists throughout the match. Store your memory on self.
        self.player_id = view.player_id
        self.events_seen = 0

    def on_event(self, event: PlayerEvent) -> None:
        # Events arrive separately from decisions. This hook returns no action.
        self.events_seen += 1

    def choose_action(self, view: PlayerView, options: Sequence[ActionOption]) -> Action:
        # A discard is a template: fill exactly the required number of cards.
        discard = next((a for a in options if a['type'] == 'DISCARD'), None)
        if discard:
            remaining = discard['count']
            resources: dict[Resource, int] = {}
            for resource, held in view.self.resources.items():
                count = min(held, remaining)
                if count:
                    resources[resource] = count
                    remaining -= count
                if remaining == 0:
                    break
            return {'type': 'DISCARD', 'resources': resources}

        # Finish optional decisions without initiating trades or choosing a plan.
        for action in options:
            if action['type'] == 'REJECT' or action['type'] == 'CANCEL_TRADE' or action['type'] == 'END_TURN':
                return action

        # Setup, rolling, robber moves, and card effects have concrete options.
        # Pick the first one mechanically; replace this with your own logic.
        for action in options:
            if action['type'] != 'TRADE' and action['type'] != 'COUNTER' and action['type'] != 'DISCARD':
                return action
        raise ValueError('No concrete legal action available')

    def on_game_end(self, result: GameResult) -> None:
        # Optional place to inspect the final result.
        pass
