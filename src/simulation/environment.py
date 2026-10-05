"""Local decision environment using the same engine as hosted matches."""
from ..player import Player, freeze
from ..simulator.types.identifiers import PlayerId
from .simulator import GameConfig, Simulator


class _ControlledPlayer(Player):
    def __init__(self, listener):
        self.listener = listener
        self.action = None
        self.events = []

    def on_game_start(self, view):
        if self.listener: self.listener.on_game_start(view)

    def on_event(self, event):
        self.events.append(event)
        if self.listener: self.listener.on_event(event)

    def choose_action(self, view, options):
        return self.action

    def on_game_end(self, result):
        if self.listener: self.listener.on_game_end(result)


class CatanEnv:
    """One controlled seat; opponents advance to its next decision.

    Listener callbacks preserve Player event delivery. choose_action is supplied
    externally through step. All execution is trusted, local, and in process.
    """
    def __init__(self, opponents='medium', player_id='P1', max_turns=1000,
                 max_decisions=20000, listener=None, reward_fn=None):
        self.player_id = PlayerId(player_id)
        self.opponents = opponents
        self.config = GameConfig(max_turns=max_turns, max_decisions=max_decisions)
        self.listener = listener
        self.reward_fn = reward_fn
        self.sim = None

    def reset(self, seed=42):
        from ..platform.builtin_players import load_player
        self.sim = Simulator(seed, self.config)
        self.controlled = _ControlledPlayer(self.listener)
        players = {pid: self.controlled if pid == self.player_id else
                   (load_player(self.opponents) if isinstance(self.opponents, str)
                    else self.opponents(pid)) for pid in PlayerId.all_players()}
        self.sim.register_players(players)
        self.sim.start_game()
        self._advance()
        return self._snapshot()

    def _advance(self):
        while self.sim.result is None:
            if self.sim.limit_reached():
                self.sim.step()
            elif self.sim.acting_player() == self.player_id:
                break
            else:
                self.sim.step()

    def _snapshot(self):
        view = self.sim.build_view_for_player(self.player_id)
        events = tuple(self.controlled.events)
        self.controlled.events.clear()
        return view, freeze({'legal_actions': [] if self.sim.result else self.sim.available_actions(),
                            'decision_id': self.sim.decision_number, 'events': events,
                            'result': self.sim.result})

    def step(self, action):
        if self.sim is None: raise RuntimeError('Call reset before step')
        if self.sim.result is not None: raise RuntimeError('Episode ended; call reset')
        previous = self.sim.build_view_for_player(self.player_id)
        self.controlled.action = action
        self.sim.step()
        self._advance()
        view, info = self._snapshot()
        result = self.sim.result
        terminated = bool(result and result['status'] != 'stopped')
        truncated = bool(result and result['status'] == 'stopped')
        reward = (1.0 if result['winner'] == self.player_id.value else -1.0) if result and result['status'] == 'completed' else 0.0
        if self.reward_fn:
            reward = self.reward_fn(previous, action, view, info)
        return view, reward, terminated, truncated, info
