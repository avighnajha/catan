"""Local play and batch evaluation; never connects to a server."""
import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import sys
import time
import subprocess

from ..platform.builtin_players import LEVELS, load_player
from ..platform.recording import RecordingSimulator
from ..player.process import ProcessPlayer
from ..simulation.simulator import GameConfig
from .terminal import board_text
from .types.identifiers import PlayerId
from .local_player import DiagnosticPlayer, load_local_player


def run_match(args, seed, seat):
    sim = RecordingSimulator(seed, GameConfig(max_turns=args.max_turns, max_decisions=args.max_decisions))
    players = {}
    start = time.perf_counter()
    process=None
    original_path=list(sys.path)
    try:
        stream=open(os.devnull,'w') if args.quiet_player else sys.stderr
        if args.debug:
            implementation=load_local_player(args.player,stream)
        else:
            process=implementation=ProcessPlayer(Path(args.player).read_text(encoding='utf-8'),
                         timeout=args.timeout,trusted_local=True,log_stream=stream,
                         source_path=args.player)
        diagnostic=DiagnosticPlayer(implementation,stream)
        for pid in PlayerId.all_players():
            players[pid] = diagnostic if pid.value==seat else load_player(args.opponents)
        sim.register_players(players)
        sim.begin_recording()
        color = args.color=='always' or (args.color=='auto' and sys.stdout.isatty())
        if args.verbose:
            print('Initial board\n'+board_text(sim,color))
            sim.event_bus.subscribe(lambda e: print(f'{e.turn_number} {e.player_id.value if e.player_id else ""} {e.event_type} {json.dumps(e.data)}') if e.visibility=='PUBLIC' else None)
            shown = [False]
            def show_setup(label):
                if not shown[0] and not sim.stage.startswith('SETUP'):
                    shown[0] = True
                    print('After initial placement\n'+board_text(sim,color))
            sim.subscribe(show_setup)
        result = dict(sim.run())
        if result['status']=='player_failed':
            result['failure_context']=json.loads(json.dumps(diagnostic.failure or diagnostic.context,default=repr))
        sim.assert_invariants()
        result.update(seed=seed, player_id=seat,
                      turns_completed=max(0,sim.game_state.turn_state.turn_number-1),
                      scores={p.player_id.value:p.get_calculated_victory_points() for p in sim.game_state.players},
                      runtime_seconds=round(time.perf_counter()-start,3))
        if args.replay:
            Path(args.replay).write_text(json.dumps(sim.export_recording({'seed':seed,'game_id':sim.game_state.game_id})),encoding='utf-8')
        if args.audit:
            Path(args.audit).write_text(json.dumps(sim.export_private_audit()),encoding='utf-8')
        return result
    finally:
        if process: process.close()
        sys.path[:]=original_path
        if 'stream' in locals() and args.quiet_player: stream.close()


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if argv==['--update']: argv=['update']
    parser = argparse.ArgumentParser(description='Run Catan locally, without an account or server')
    sub = parser.add_subparsers(dest='command',required=True)
    sub.add_parser('update',help='Update the installed simulator (requires internet and Git)')
    for command in ('play','evaluate'):
        p = sub.add_parser(command)
        p.add_argument('--player',required=True,help='Python Player file')
        p.add_argument('--opponents',choices=LEVELS,default='medium')
        p.add_argument('--seed',type=int,default=42)
        p.add_argument('--max-turns',type=int,default=1000,help='Normal player turns; 0 completes setup only')
        p.add_argument('--max-decisions',type=int,default=20000)
        p.add_argument('--timeout',type=float,default=2.0,help='Player callback timeout in seconds')
        p.add_argument('--debug',action='store_true',help='Run player in this process for breakpoints; no callback timeout')
        p.add_argument('--quiet-player',action='store_true',help='Suppress player prints (normally shown on stderr)')
        p.add_argument('--output',choices=('summary','json'),default='summary')
        p.add_argument('--results',help='Write machine-readable results JSON')
        p.set_defaults(verbose=False,color='auto',replay=None,audit=None)
        if command=='play':
            p.add_argument('--seat',choices=('P1','P2','P3','P4'),default='P1')
            p.add_argument('--verbose',action='store_true',help='Board and public events')
            p.add_argument('--color',choices=('auto','always','never'),default='auto')
            p.add_argument('--replay')
            p.add_argument('--audit',help='Private debugging data; do not publish')
        else:
            p.add_argument('--games',type=int,default=100,help='Total matches; seats rotate P1 through P4')
    args = parser.parse_args(argv)
    if args.command=='update':
        from .update import update_installation
        try: return update_installation()
        except (OSError,RuntimeError,subprocess.CalledProcessError) as error:
            parser.exit(2,f'Update failed: {error}\nNo reset or forced Git changes were performed.\n')
    if args.max_turns<0 or args.max_decisions<=0: parser.error('Use nonnegative max-turns and positive max-decisions')
    import math
    if not math.isfinite(args.timeout) or args.timeout<=0: parser.error('timeout must be a finite positive number')
    if args.verbose and args.output=='json': parser.error('Use summary output with verbose; --results can save JSON separately')
    if args.command=='evaluate' and args.games<=0: parser.error('games must be positive')
    try:
        runs = [run_match(args,args.seed+i//4,f'P{i%4+1}') for i in range(args.games)] if args.command=='evaluate' else [run_match(args,args.seed,args.seat)]
    except (OSError,ValueError,RuntimeError) as error:
        parser.exit(2,f'{error}\n')
    statuses = Counter(r['status'] for r in runs)
    wins = sum(r['winner']==r['player_id'] for r in runs)
    seats = defaultdict(lambda: {'games':0,'completed':0,'wins':0})
    for r in runs:
        s = seats[r['player_id']]; s['games']+=1
        s['completed']+=r['status']=='completed'; s['wins']+=r['winner']==r['player_id']
    output = runs[0] if args.command=='play' else {'games':len(runs),'statuses':dict(statuses),'wins':wins,
                'average_score':sum(r['scores'][r['player_id']] for r in runs)/len(runs),
                'average_turns_completed':sum(r['turns_completed'] for r in runs)/len(runs),
                'runtime_seconds':round(sum(r['runtime_seconds'] for r in runs),3),
                'seats':dict(seats),'runs':runs}
    if args.results: Path(args.results).write_text(json.dumps(output,indent=2),encoding='utf-8')
    if args.output=='json': print(json.dumps(output))
    elif args.command=='play':
        r=runs[0]
        print(f"{r['status']}: {r['reason']} | seed {r['seed']} | seat {r['player_id']} | winner {r['winner'] or '-'} | turns completed {r['turns_completed']} | {r['runtime_seconds']}s")
        print('Scores: '+json.dumps(r['scores']))
    else:
        print(f'Games: {len(runs)} | statuses: {dict(statuses)} | wins: {wins}/{statuses["completed"]} completed | average score: {output["average_score"]:.2f}')
        print('By seat: '+json.dumps(dict(seats)))
    if args.output=='summary':
        for r in runs:
            context=r.get('failure_context')
            if not context: continue
            print(f"Failure details (seed {r['seed']}, seat {r['player_id']}):",file=sys.stderr)
            if 'traceback' in context:
                print(context['traceback'],file=sys.stderr)
            else:
                print(f"Decision {context['decision_id']} in {context['phase']}; available: {', '.join(context['available_types'])}",file=sys.stderr)
                print('Returned: '+json.dumps(context.get('returned_action'),default=repr),file=sys.stderr)
    return 1 if statuses['player_failed'] or statuses['failed'] else 0


if __name__=='__main__':
    raise SystemExit(main())
