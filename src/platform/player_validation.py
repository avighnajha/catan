"""Three-stage player checks. Uses no rooms, replay store or account statistics."""
import time
from ..player.example import ExamplePlayer
from ..player.hosted import hosted_player
from ..simulation.simulator import Simulator, GameConfig
from ..simulator.types.identifiers import PlayerId
from ..simulator.types.resource import ResourceType as R, DevelopmentCardType as D


class ValidationFailure(Exception):
    def __init__(self, details):
        super().__init__(details['error'])
        self.details=details


def check_failure(sim, name):
    if sim.failures:
        raise ValidationFailure(dict(sim.failures[0],scenario=name))
    if sim.result and sim.result['status'] not in ('completed','stopped'):
        raise ValidationFailure({'error':sim.result['reason'],'scenario':name})


def give(sim,pid,resources):
    values={R(r):n for r,n in resources.items()}
    sim._grant(pid,values)
    sim._emit('ResourcesProduced',{'resources':resources},pid)
    sim._flush('Validation resource fixture')
    check_failure(sim,sim._validation_scenario)


def apply(sim,kind,**fields):
    sim.apply_action(sim.acting_player(),{'type':kind,**fields})
    check_failure(sim,sim._validation_scenario)


def roll(sim,total=8):
    original=sim.rng.randint
    sim.rng.randint=lambda a,b: total//2
    if total==7:
        dice=iter((3,4));sim.rng.randint=lambda a,b:next(dice)
    try: apply(sim,'ROLL')
    finally: sim.rng.randint=original


def gift_card(sim,kind):
    sim.development_deck.remove(kind)
    sim.bank.development_cards[kind]-=1
    sim.player(sim.active).development_cards[kind]+=1
    sim._emit('DevelopmentCardDrawn',{'card':kind.value},sim.active,'PLAYER_ONLY')
    sim._flush('Validation development card fixture')
    check_failure(sim,sim._validation_scenario)


SCENARIOS=(
    'Initial placement and pre-roll','Ordinary turn and bank trades','Discard after seven',
    'Robber movement','Year of Plenty','Year of Plenty with a depleted bank',
    'Road Building','Monopoly','Respond to an affordable trade',
    'Respond to an unaffordable trade','Select acceptance or counteroffer','All recipients reject',
)


def scenario(code,name,factory=hosted_player):
    player=factory(code)
    sim=Simulator(20,GameConfig(max_turns=1000))
    sim._validation_scenario=name
    sim.register_players({pid:player if pid==PlayerId.P1 else ExamplePlayer() for pid in PlayerId.all_players()})
    try:
        sim.start_game();check_failure(sim,name)
        while sim.stage.startswith('SETUP'):
            sim.step();check_failure(sim,name)
        if name=='Initial placement and pre-roll':
            sim.step()
        elif name=='Discard after seven':
            give(sim,PlayerId.P1,{'WOOD':10});roll(sim,7)
            sim.step()
        else:
            roll(sim)
            # Eight avoids forced discard, and P1 is still the active player.
            if name=='Ordinary turn and bank trades':
                give(sim,PlayerId.P1,{r.value:3 for r in R});sim.step()
            elif name=='Robber movement':
                gift_card(sim,D.KNIGHT);apply(sim,'PLAY_DEVELOPMENT_CARD',card='KNIGHT');sim.step()
            elif name.startswith('Year of Plenty'):
                if name.endswith('depleted bank'):
                    for r in R:
                        keep=1 if r==R.WOOD else 0
                        n=sim.bank.resources[r]-keep
                        if n: give(sim,PlayerId.P2,{r.value:n})
                gift_card(sim,D.YEAR_OF_PLENTY)
                apply(sim,'PLAY_DEVELOPMENT_CARD',card='YEAR_OF_PLENTY');sim.step()
            elif name=='Road Building':
                gift_card(sim,D.ROAD_BUILDING)
                apply(sim,'PLAY_DEVELOPMENT_CARD',card='ROAD_BUILDING')
                while sim.stage=='FREE_ROAD' and not sim.result: sim.step();check_failure(sim,name)
            elif name=='Monopoly':
                gift_card(sim,D.MONOPOLY);apply(sim,'PLAY_DEVELOPMENT_CARD',card='MONOPOLY');sim.step()
            elif name.startswith('Respond to'):
                # P2 proposes to the submitted player on P2's own turn.
                apply(sim,'END_TURN');roll(sim)
                give(sim,PlayerId.P2,{'WOOD':2})
                if name=='Respond to an affordable trade': give(sim,PlayerId.P1,{'ORE':1})
                else:
                    amount=sim.player(PlayerId.P1).resources[R.ORE]
                    if amount: sim._pay(PlayerId.P1,{R.ORE:amount})
                apply(sim,'TRADE',recipients=['P1'],give={'WOOD':1},receive={'ORE':1})
                sim.step()
            else:
                give(sim,PlayerId.P1,{'WOOD':2})
                give(sim,PlayerId.P2,{'ORE':2});give(sim,PlayerId.P3,{'ORE':2})
                apply(sim,'TRADE',recipients=['P2','P3'],give={'WOOD':1},receive={'ORE':1})
                if name=='All recipients reject': apply(sim,'REJECT');apply(sim,'REJECT')
                else: apply(sim,'ACCEPT');apply(sim,'COUNTER',give={'ORE':2},receive={'WOOD':2})
                sim.step()
        check_failure(sim,name)
        sim.assert_invariants()
        if sim.result is None: sim._finish('stopped','Validation scenario finished')
        check_failure(sim,name)
    finally:
        player.close()


def validate(code,progress,factory=hosted_player):
    """Progress callbacks receive only owner-private diagnostics, never saved games."""
    stage='quick'
    try:
        progress(stage,'running','Checking source and player startup')
        compile(code,'uploaded-player.py','exec')
        player=factory(code)
        try:
            sim=Simulator(20)
            sim.register_players({p:player if p==PlayerId.P1 else ExamplePlayer() for p in PlayerId.all_players()})
            sim.step();check_failure(sim,'Initial decision')
            if sim.result is None: sim._finish('stopped','Quick validation finished')
            check_failure(sim,'Lifecycle callbacks')
        finally: player.close()
        progress(stage,'passed','Syntax, loading, lifecycle, events and initial decision passed')
        stage='scenarios'
        for i,name in enumerate(SCENARIOS):
            progress(stage,'running',name,completed=i,total=len(SCENARIOS))
            scenario(code,name,factory)
        progress(stage,'passed',f'{len(SCENARIOS)} scenarios passed',completed=len(SCENARIOS),total=len(SCENARIOS))
        stage='games';games=[]
        for i,seed in enumerate((20,42,137)):
            progress(stage,'running',f'Running game {i+1} of 3',completed=i,total=3,games=games)
            player=factory(code)
            try:
                seat=PlayerId.all_players()[i]
                sim=Simulator(seed,GameConfig(max_turns=1000))
                sim.register_players({p:player if p==seat else ExamplePlayer() for p in PlayerId.all_players()})
                started=time.monotonic()
                while sim.result is None:
                    if time.monotonic()-started>180:
                        raise ValidationFailure({'error':'Game exceeded the hosted 180-second execution limit',
                            'scenario':f'Game {i+1}, seed {seed}, seat {seat.value}','category':'execution_limit'})
                    sim.step()
                check_failure(sim,f'Game {i+1}, seed {seed}, seat {seat.value}')
                sim.assert_invariants()
                games.append({'seed':seed,'seat':seat.value,'status':sim.result['status'],
                              'turns':sim.result['turn_count'],'winner':sim.result['winner']})
            finally: player.close()
        limited=sum(g['status']=='stopped' for g in games)
        progress(stage,'passed','3 games checked'+(f'; {limited} reached a simulation limit without an invalid action' if limited else ''),
                 completed=3,total=3,games=games)
        return True
    except Exception as error:
        import traceback
        details=getattr(error,'details',None) or {'error':str(error),
            'traceback':getattr(error,'player_diagnostics','') or traceback.format_exc()}
        progress(stage,'failed',details['error'],details=details)
        return False
