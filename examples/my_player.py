"""Runnable interface demonstration. Add your own decision logic here."""
from src.player import Player


class MyPlayer(Player):
    def on_game_start(self, view):
        # One instance persists throughout the match. Store your memory on self.
        self.player_id = view.player_id
        self.events_seen = 0

    def on_event(self, event):
        # Events arrive separately from decisions. This hook returns no action.
        self.events_seen += 1

    def choose_action(self, view, options):
        # A discard is a template: fill exactly the required number of cards.
        discard = next((a for a in options if a.type == 'DISCARD'), None)
        if discard:
            remaining = discard.count
            resources = {}
            for resource, held in view.self.resources.items():
                count = min(held, remaining)
                if count:
                    resources[resource] = count
                    remaining -= count
                if remaining == 0:
                    break
            return {'type': 'DISCARD', 'resources': resources}

        # Finish optional decisions without initiating trades or choosing a plan.
        for kind in ('REJECT', 'CANCEL_TRADE', 'END_TURN'):
            action = next((a for a in options if a.type == kind), None)
            if action:
                return action

        # Setup, rolling, robber moves, and card effects have concrete options.
        # Pick the first one mechanically; replace this with your own logic.
        return next(a for a in options if a.type not in ('TRADE', 'COUNTER'))

    def on_game_end(self, result):
        # Optional place to inspect the final result.
        pass
