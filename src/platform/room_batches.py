"""Fair bounded scheduling and finished-match statistics for reusable rooms."""
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
import threading

ACTIVE = ('queued', 'running')
METRICS = ('points', 'roads', 'settlements', 'cities', 'settlements_built', 'dev_cards_played')


class FairMatchQueue:
    """Round-robin batches, at most two isolated match workers globally."""
    def __init__(self, max_workers=2):
        self.pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='catan-match')
        self.capacity = max_workers
        self.active = 0
        self.pending = deque()
        self.lock = threading.RLock()
        self.idle = threading.Event()
        self.idle.set()

    def submit_batch(self, callback, jobs):
        with self.lock:
            self.idle.clear()
            self.pending.append((callback, deque(jobs)))
            self._pump()

    def _pump(self):
        while self.active < self.capacity and self.pending:
            callback, jobs = self.pending.popleft()
            job = jobs.popleft()
            if jobs: self.pending.append((callback, jobs))
            self.active += 1
            self.pool.submit(self._execute, callback, job)

    def _execute(self, callback, job):
        try:
            callback(*job)
        finally:
            with self.lock:
                self.active -= 1
                self._pump()
                if not self.active and not self.pending: self.idle.set()

    def shutdown(self):
        self.idle.wait()
        self.pool.shutdown(wait=True)


def summarize_match(sim, recording):
    events = recording['events']
    return [{'player_id': p.player_id.value, 'points': p.get_calculated_victory_points(),
             'roads': len(p.roads), 'settlements': len(p.settlements), 'cities': len(p.cities),
             'settlements_built': sum(e['type'] == 'SettlementBuilt' and e['player_id'] == p.player_id.value for e in events),
             'dev_cards_played': sum(e['type'] == 'DevelopmentCardPlayed' and e['player_id'] == p.player_id.value for e in events),
             'score_visibility': 'final'} for p in sim.game_state.players]


def match_summary(game, store):
    if 'summary' in game: return game['summary']
    if not game.get('replay_available'): return []
    replay = store.replay(game['game_id'])
    if not replay: return []
    events = replay.get('events', [])
    return [dict(p, points=p['victory_points'], score_visibility='public',
                 settlements_built=sum(e['type'] == 'SettlementBuilt' and e['player_id'] == p['player_id'] for e in events),
                 dev_cards_played=sum(e['type'] == 'DevelopmentCardPlayed' and e['player_id'] == p['player_id'] for e in events))
            for p in replay['result']['statistics']['players']]


def group_batches(games):
    groups = {}
    for game in games:
        key = game.get('batch_id') or game['game_id']
        groups.setdefault(key, []).append(game)
    result = []
    for key, matches in groups.items():
        matches.sort(key=lambda g: g.get('batch_index', 1))
        statuses = Counter(g['status'] for g in matches)
        active = sum(statuses[s] for s in ACTIVE)
        result.append({'batch_id': key, 'number': matches[0].get('batch_number'),
                       'matches': matches, 'total': len(matches), 'finished': len(matches)-active,
                       'active': bool(active), 'statuses': dict(statuses),
                       'rotate_seats': matches[0].get('rotate_seats', False)})
    return result


def aggregate(games, store):
    players = {}
    for game in reversed(games):
        summaries = {p['player_id']: p for p in match_summary(game, store)}
        for participant in game.get('participants', []):
            seat = participant.get('room_seat') or int(participant['player_id'][1:])
            identity = participant.get('user_id') or f"{game.get('room_id')}:seat-{seat}"
            key = (identity, participant.get('bot_id'))
            item = players.setdefault(key, {'name': participant['name'], 'bot_id': participant.get('bot_id'),
                'bot_name': participant.get('bot_name'), 'bot_version': participant.get('bot_version'),
                'color': participant.get('color'), 'runs': []})
            summary = summaries.get(participant['player_id'], {})
            item['runs'].append({'game_id': game['game_id'], 'seed': game['seed'],
                'match_number': game.get('room_match_number'), 'batch_id': game.get('batch_id'),
                'player_id': participant['player_id'], 'status': game['status'],
                'won': game['status'] == 'completed' and game.get('winner') == participant['player_id'],
                'score_visibility': summary.get('score_visibility'),
                **{metric: summary.get(metric) for metric in METRICS}})
    for item in players.values():
        runs = item['runs']
        item['completed_games'] = sum(r['status'] == 'completed' for r in runs)
        item['wins'] = sum(r['won'] for r in runs)
        item['win_rate'] = round(100*item['wins']/item['completed_games'], 1) if item['completed_games'] else None
        item['statuses'] = dict(Counter(r['status'] for r in runs))
        item['totals'], item['averages'], item['ranges'] = {}, {}, {}
        for metric in METRICS:
            values = [r[metric] for r in runs if r[metric] is not None]
            item['totals'][metric] = sum(values) if values else None
            item['averages'][metric] = round(sum(values)/len(values), 2) if values else None
            item['ranges'][metric] = [min(values), max(values)] if values else None
    return {'matches': len(games), 'statuses': dict(Counter(g['status'] for g in games)),
            'players': list(players.values())}
