"""Local decision environment using the same engine as hosted matches."""
from ..player import Player, freeze
from ..simulator.types.identifiers import PlayerId
from .simulator import GameConfig, Simulator


class _ControlledPlayer(Player):
    def __init__(self, listener, player=None):
        self.listener = listener
        self.player = player
        self.protocol_version = player.protocol_version if player else Player.protocol_version
        self.action = None
        self.events = []

    def on_game_start(self, view):
        if self.player: self.player.on_game_start(view)
        if self.listener: self.listener.on_game_start(view)

    def on_event(self, event):
        self.events.append(event)
        if self.player: self.player.on_event(event)
        if self.listener: self.listener.on_event(event)

    def choose_action(self, view, options):
        return self.player.choose_action(view, options) if self.player else self.action

    def on_game_end(self, result):
        if self.player: self.player.on_game_end(result)
        if self.listener: self.listener.on_game_end(result)


class CatanEnv:
    """Local games with automatic Player callbacks or external action control.

    With player_factory, reset stops before setup decisions and run_* methods
    drive all seats. Without it, reset/step preserve the RL decision interface.
    All execution is trusted, local, and in process.
    """
    def __init__(self, opponents='medium', player_id='P1', max_turns=1000,
                 max_decisions=20000, listener=None, reward_fn=None,
                 player_factory=None):
        self.player_id = PlayerId(player_id)
        self.opponents = opponents
        self.config = GameConfig(max_turns=max_turns, max_decisions=max_decisions)
        self.listener = listener
        self.reward_fn = reward_fn
        self.player_factory = player_factory
        self.sim = None

    def reset(self, seed=42):
        from ..platform.builtin_players import load_player
        self.sim = Simulator(seed, self.config)
        player = self.player_factory() if self.player_factory is not None else None
        if self.player_factory is not None and not isinstance(player, Player):
            raise TypeError('player_factory must create a Player instance')
        if player is not None and player is self.listener:
            raise ValueError('The player and optional listener must be separate instances')
        self.controlled = _ControlledPlayer(self.listener, player)
        players = {pid: self.controlled if pid == self.player_id else
                   (load_player(self.opponents) if isinstance(self.opponents, str)
                    else self.opponents(pid)) for pid in PlayerId.all_players()}
        if player is not None and any(p is player for p in players.values()):
            raise ValueError('Each seat needs its own player instance')
        self.sim.register_players(players)
        self.sim.start_game()
        if self.player_factory is None: self._advance()
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
        acting = None if self.sim.result else self.sim.acting_player()
        return view, freeze({'legal_actions': self.sim.available_actions() if acting == self.player_id else [],
                            'acting_player': acting, 'phase': self.sim.stage,
                            'turn_number': self.sim.game_state.turn_state.turn_number,
                            'round_number': (self.sim.game_state.turn_state.turn_number - 1) // 4 + 1,
                            'decision_id': self.sim.decision_number, 'events': events,
                            'result': self.sim.result})

    def step(self, action):
        if self.player_factory is not None:
            raise RuntimeError('step(action) requires external control; omit player_factory or use run_step()')
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

    def _require_runner(self):
        if self.sim is None: raise RuntimeError('Call reset before running')
        if self.player_factory is None:
            raise RuntimeError('Automatic runners require player_factory; use step(action) for external control')

    def _stop_at_limit(self):
        if self.sim.result is None and self.sim.limit_reached(): self.sim.step()

    def _setup(self):
        while self.sim.result is None and self.sim.stage.startswith('SETUP'):
            self.sim.step()
        self._stop_at_limit()

    def run_step(self):
        """Process one pending decision, including an opponent response."""
        self._require_runner()
        self.sim.step()
        self._stop_at_limit()
        return self._snapshot()

    def run_setup(self):
        """Finish initial placement; stop before the first normal decision."""
        self._require_runner()
        self._setup()
        return self._snapshot()

    def run_turn(self):
        """Finish setup if necessary, then the current normal player turn."""
        self._require_runner()
        self._setup()
        turn = self.sim.game_state.turn_state.turn_number
        while self.sim.result is None and self.sim.game_state.turn_state.turn_number == turn:
            self.sim.step()
        self._stop_at_limit()
        return self._snapshot()

    def run_round(self):
        """Finish setup if necessary, then the current P1-through-P4 round."""
        self._require_runner()
        self._setup()
        next_round = ((self.sim.game_state.turn_state.turn_number - 1) // 4 + 1) * 4 + 1
        while self.sim.result is None and self.sim.game_state.turn_state.turn_number < next_round:
            self.sim.step()
        self._stop_at_limit()
        return self._snapshot()

    def run(self):
        """Finish the remaining game and return its immutable result."""
        self._require_runner()
        return freeze(self.sim.run())
