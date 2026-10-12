import {test,expect} from '@playwright/test';
import {completeBoardFixture} from './complete-board-fixture.js';

const playerCode=`from src.player.example import ExamplePlayer
class BrowserPlayer(ExamplePlayer):
    pass
`;

test('reusable private room runs a batch, navigates matches, shows statistics and rematches',async({page})=>{
  test.setTimeout(180000);
  const suffix=Date.now().toString(36),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/');
  await register(page,`Batch-${suffix}`,`batch-${suffix}@example.com`);
  await uploadBot(page,`Batch player ${suffix}`);
  await page.getByRole('button',{name:'Test your player',exact:true}).click();
  await page.getByRole('button',{name:'Create private test room',exact:true}).click();
  await expect(page).toHaveURL(/#room\//);
  const roomUrl=page.url();
  await page.getByLabel('Starting seed',{exact:true}).fill('20');
  await page.getByRole('button',{name:'Shuffle seed',exact:true}).click();
  await expect(page.getByLabel('Starting seed',{exact:true})).not.toHaveValue('20');
  await page.getByLabel('Starting seed',{exact:true}).fill('20');
  await page.getByLabel('Matches',{exact:true}).fill('3');
  await page.getByLabel('Rotate starting seats',{exact:true}).check();
  await page.getByRole('button',{name:'Run 3 matches →',exact:true}).click();
  await expect(page.getByRole('navigation',{name:'Batch matches'}).locator('a')).toHaveCount(3,{timeout:30000});
  await expect(page.locator('#timeline')).toBeVisible({timeout:90000});
  const navigation=page.getByRole('navigation',{name:'Batch matches'});
  const secondMatch=navigation.getByRole('link',{name:/Match 2/});
  const secondId=(await secondMatch.getAttribute('href')).split('/')[1];
  const sidebar=await page.locator('#batchNavigation').elementHandle();
  let releaseNavigation;
  const navigationGate=new Promise(resolve=>releaseNavigation=resolve);
  let navigationHandled;
  const navigationFinished=new Promise(resolve=>navigationHandled=resolve);
  const batchRoute=`**/games/${secondId}/batch`;
  await page.route(batchRoute,async route=>{await navigationGate;await route.continue();navigationHandled();});
  try{
    await secondMatch.click();
    await expect(page.locator('.viewer-head .highlight')).toHaveText('/ 21',{timeout:90000});
    await expect(page.locator('#timeline')).toHaveValue('0',{timeout:90000});
    // Slow navigation metadata must not remove the sidebar or shift the board.
    expect(await sidebar.evaluate(element=>element.isConnected)).toBe(true);
    await expect(page.getByRole('navigation',{name:'Batch matches'}).locator('a')).toHaveCount(3);
  }finally{releaseNavigation();}
  await navigationFinished;
  await page.unrouteAll({behavior:'wait'});
  await expect(page.locator('[aria-current=page]')).toContainText('Match 2');
  await expect(page.getByRole('button',{name:'Replay same seed',exact:true})).toBeEnabled({timeout:90000});
  await page.screenshot({path:'test-results/room-batch-replay.png',fullPage:true});
  const secondUrl=page.url();
  await page.goto(roomUrl);
  await expect(page.locator('.room-history')).toContainText('3 matches');
  await page.getByRole('button',{name:'Batch statistics',exact:true}).click();
  await expect(page.locator('#modalBody')).toContainText('3 matches');
  const breakdown=page.locator('.run-breakdown').first();
  await breakdown.locator('summary').click();
  await expect(breakdown.locator('table').last().locator('tbody tr')).toHaveCount(3);
  await expect(breakdown).toContainText('Settlements built');
  await page.getByRole('button',{name:'Close dialog',exact:true}).click();
  await page.screenshot({path:'test-results/room-batch-history.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'test-results/room-batch-mobile.png',fullPage:true});
  await page.setViewportSize({width:1440,height:1050});
  await page.goto(secondUrl);
  await page.getByRole('button',{name:'Replay same seed',exact:true}).click();
  await expect(page).not.toHaveURL(secondUrl);
  await expect(page.getByRole('navigation',{name:'Batch matches'})).toContainText('Seed 21');
  await expect(page.locator('#timeline')).toBeVisible({timeout:90000});
  await page.goto(roomUrl);
  await expect(page.locator('.room-history')).toContainText('4 matches');
  await expect(page.locator('.batch-history')).toHaveCount(2);
  expect(errors).toEqual([]);
});

test('constant-seed batch settings persist and its private room can be deleted without losing replays',async({page})=>{
  test.setTimeout(120000);
  const suffix=Date.now().toString(36);
  await page.goto('/');
  await register(page,`Fixed-${suffix}`,`fixed-${suffix}@example.com`);
  await uploadBot(page,`Fixed seed player ${suffix}`);
  await page.getByRole('button',{name:'Test your player',exact:true}).click();
  await page.getByRole('button',{name:'Create private test room',exact:true}).click();
  await expect(page).toHaveURL(/#room\//);
  const roomUrl=page.url();
  await page.getByLabel('Starting seed',{exact:true}).fill('31');
  await page.getByLabel('Matches',{exact:true}).fill('3');
  await page.getByLabel('Use the same seed for every match',{exact:true}).check();
  await page.getByLabel('Rotate starting seats',{exact:true}).check();
  await page.reload();
  await expect(page.getByLabel('Use the same seed for every match',{exact:true})).toBeChecked();
  await expect(page.getByLabel('Rotate starting seats',{exact:true})).toBeChecked();
  await expect(page.getByLabel('Starting seed',{exact:true})).toHaveValue('31');
  await page.getByRole('button',{name:'Run 3 matches →',exact:true}).click();
  const links=page.getByRole('navigation',{name:'Batch matches'}).locator('a');
  await expect(links).toHaveCount(3);
  for(let index=0;index<3;index++)await expect(links.nth(index)).toContainText('Seed 31');
  await expect(page.locator('#timeline')).toBeVisible({timeout:90000});
  await expect(page.getByRole('button',{name:'Replay same seed',exact:true})).toBeEnabled({timeout:90000});
  const matchUrl=page.url();
  await page.goto(roomUrl);
  await expect(page.locator('.batch-history summary')).toContainText('same seed');
  await page.screenshot({path:'test-results/constant-seed-room.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.setViewportSize({width:1440,height:1050});
  await page.getByRole('button',{name:'Delete room',exact:true}).click();
  await expect(page.getByRole('dialog')).toContainText('Saved matches stay in your match archive');
  await page.getByRole('button',{name:'Cancel',exact:true}).click();
  await expect(page).toHaveURL(roomUrl);
  await page.getByRole('button',{name:'Delete room',exact:true}).click();
  await page.getByRole('dialog').getByRole('button',{name:'Delete room',exact:true}).click();
  await expect(page).toHaveURL(/#rooms$/);
  await expect(page.locator(`a[href="#${new URL(roomUrl).hash.slice(1)}"]`)).toHaveCount(0);
  await page.goto(matchUrl);
  await expect(page.locator('#timeline')).toBeVisible();
  await expect(page.locator('#rematchControls')).toContainText('This room was deleted');
  await expect(page.getByRole('button',{name:'Replay same seed',exact:true})).toHaveCount(0);
  await expect(page.getByRole('navigation',{name:'Batch matches'}).locator('a')).toHaveCount(3);
});

test('long replay turn labels stay readable and clickable on desktop and mobile',async({page})=>{
  const {metadata,replay}=completeBoardFixture(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  metadata.room_id=null;
  const state=replay.frames[1].state;
  replay.frames=Array.from({length:475},(_,index)=>({sequence:index,label:`Recorded action ${index}`,state:{...structuredClone(state),turn_number:Math.floor(index/2)+1},events:[]}));
  await page.route('**/games/game-fixture',route=>route.fulfill({json:metadata}));
  await page.route('**/game/game-fixture/replay',route=>route.fulfill({json:replay}));
  await page.goto('/#match/game-fixture');
  const markers=page.locator('#markers button');
  const labelBounds=()=>markers.evaluateAll(buttons=>buttons.map(button=>{const box=button.getBoundingClientRect();return {left:box.left,right:box.right};}));
  const checkSpacing=async()=>{
    const bounds=await labelBounds();
    expect(bounds.length).toBeGreaterThan(2);
    for(let index=1;index<bounds.length;index++)expect(bounds[index].left-bounds[index-1].right).toBeGreaterThanOrEqual(8);
  };
  await expect(markers.first()).toHaveText('1');
  await expect(markers.last()).toHaveText('238');
  await checkSpacing();
  const desktopCount=await markers.count();
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>markers.count()).toBeLessThan(desktopCount);
  await checkSpacing();
  await expect(markers.last()).toHaveText('238');
  const turn=Number(await markers.nth(1).textContent());
  await markers.nth(1).click();
  await expect(page.locator('#timeline')).toHaveValue(String((turn-1)*2));
  await page.getByRole('button',{name:'Next turn',exact:true}).click();
  await expect(page.locator('#turnBadge')).toHaveText(`TURN ${turn+1}`);
  await page.locator('.playback').screenshot({path:'test-results/long-replay-timeline-mobile.png'});
  await page.setViewportSize({width:1440,height:1050});
  await expect.poll(()=>markers.count()).toBe(desktopCount);
  await checkSpacing();
  await page.locator('.playback').screenshot({path:'test-results/long-replay-timeline-desktop.png'});
  expect(errors).toEqual([]);
});

test('match report expands played cards and inspects five resources for each player',async({page})=>{
  const {metadata,replay}=completeBoardFixture();
  const events=[
    {type:'DevelopmentCardPlayed',player_id:'P1',data:{card:'KNIGHT'}},
    {type:'DevelopmentCardPlayed',player_id:'P1',data:{card:'KNIGHT'}},
    {type:'DevelopmentCardPlayed',player_id:'P1',data:{card:'ROAD_BUILDING'}},
    {type:'DevelopmentCardPlayed',player_id:'P2',data:{card:'MONOPOLY'}}
  ];
  const state=replay.frames[1].state;
  replay.frames=[0,2,5,1,3].map((wood,index)=>{
    const snapshot=structuredClone(state);snapshot.phase=index===0?'SETUP_FIRST':index===4?'GAME_OVER':'NORMAL_PLAY';
    snapshot.turn_number=index===4?2:1;
    snapshot.players.forEach((p,i)=>{p.resources={WOOD:wood+i*10,BRICK:1,SHEEP:2,WHEAT:3,ORE:4};p.resource_count=wood+i*10+10;});
    return {sequence:index,label:index===2?'Trade completed':`Recorded action ${index}`,state:snapshot,events:index===2?events:[]};
  });
  replay.events=events;replay.result.statistics.players=replay.frames.at(-1).state.players;
  await page.route('**/games/game-fixture',route=>route.fulfill({json:metadata}));
  await page.route('**/game/game-fixture/replay',route=>route.fulfill({json:replay}));
  await page.goto('/#match/game-fixture');
  await page.getByRole('button',{name:'Show results ↗',exact:true}).click();
  const ada=page.locator('.dev-card-list details').filter({has:page.locator('summary',{hasText:'Ada'})});
  await expect(ada.locator('summary')).toContainText('3 played');
  await ada.locator('summary').click();
  await expect(ada.locator('dl>div').filter({hasText:'Knight'}).locator('dd')).toHaveText('2');
  await expect(ada.locator('dl>div').filter({hasText:'Road building'}).locator('dd')).toHaveText('1');
  const history=page.locator('#resourceHistory');
  await expect(history.getByRole('tab')).toHaveCount(4);
  await expect(history.locator('[data-series]')).toHaveCount(5);
  await history.getByRole('slider',{name:'Resource history position'}).fill('2');
  await expect(history.locator('.chart-position')).toContainText('Turn 1 · Trade completed');
  await expect(history.locator('.chart-counts>span').filter({hasText:'Wood'})).toContainText('5');
  await history.getByLabel('Wood',{exact:true}).uncheck();
  await expect(history.locator('[data-series="WOOD"]')).toBeHidden();
  await history.getByRole('tab',{name:'Babbage',exact:true}).click();
  await expect(history.getByRole('tab',{name:'Babbage',exact:true})).toHaveAttribute('aria-selected','true');
  await expect(history.locator('.chart-counts>span').filter({hasText:'Wood'})).toContainText('13');
  await history.getByRole('tab',{name:'Babbage',exact:true}).press('ArrowRight');
  await expect(history.getByRole('tab',{name:'Curie',exact:true})).toHaveAttribute('aria-selected','true');
  await expect(history.locator('.chart-counts>span').filter({hasText:'Wood'})).toContainText('23');
  await page.locator('#resourceHistory').screenshot({path:'test-results/match-resource-history.png'});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.locator('#resourceHistory').screenshot({path:'test-results/match-resource-history-mobile.png'});
});

test('older match report without resource snapshots explains missing history',async({page})=>{
  const {metadata,replay}=completeBoardFixture();
  await page.route('**/games/game-fixture',route=>route.fulfill({json:metadata}));
  await page.route('**/game/game-fixture/replay',route=>route.fulfill({json:replay}));
  await page.goto('/#match/game-fixture');
  await page.getByRole('button',{name:'Show results ↗',exact:true}).click();
  await expect(page.locator('#resourceHistory')).toContainText('unavailable in this older recording');
  await expect(page.locator('.dev-card-list summary')).toHaveCount(4);
});

test('edit player metadata, save changed code as a new version and remove a version',async({page})=>{
  await page.goto('/');
  const suffix=Date.now();
  await register(page,`Manager${suffix}`,`manager${suffix}@example.com`);
  await uploadBot(page,'Managed player');
  await page.getByRole('button',{name:'Edit',exact:true}).click();
  await page.getByRole('textbox',{name:'Description',exact:true}).fill('Updated player description');
  await page.getByRole('button',{name:'Save changes',exact:true}).click();
  await expect(page.locator('article.card')).toContainText('Updated player description');
  await page.getByRole('button',{name:'Edit',exact:true}).click();
  await page.getByRole('textbox',{name:'Player code',exact:true}).fill(playerCode+'\n# Updated source\n');
  await page.getByRole('button',{name:'Save changes',exact:true}).click();
  await expect(page.locator('#editBotForm .form-error')).toContainText('new version');
  await page.getByRole('textbox',{name:'New version',exact:true}).fill('v2');
  await page.getByRole('button',{name:'Save changes',exact:true}).click();
  await expect(page.locator('article.card')).toHaveCount(2);
  const original=page.locator('article.card').filter({has:page.locator('.eyebrow',{hasText:'v1'})});
  await original.getByRole('button',{name:'Remove',exact:true}).click();
  await page.getByRole('button',{name:'Cancel',exact:true}).click();
  await expect(page.locator('article.card')).toHaveCount(2);
  await original.getByRole('button',{name:'Remove',exact:true}).click();
  await page.getByRole('button',{name:'Remove player',exact:true}).click();
  await expect(page.locator('article.card')).toHaveCount(1);
  await expect(page.locator('article.card')).toContainText('v2');
});

test('failed match displays private returned-action details and traceback',async({page})=>{
  await page.goto('/');
  const suffix=Date.now();
  await register(page,`ErrorOwner${suffix}`,`errors${suffix}@example.com`);
  const me=await page.evaluate(async()=>{const r=await fetch('/auth/me',{headers:{Authorization:`Bearer ${localStorage.getItem('catan-session')}`}});return (await r.json()).user;});
  const {metadata,replay}=completeBoardFixture();
  metadata.status='failed';metadata.participants[0].user_id=me.user_id;
  await page.route('**/games/game-fixture',route=>route.fulfill({json:metadata}));
  await page.route('**/game/game-fixture/replay',route=>route.fulfill({json:replay}));
  await page.route('**/games/game-fixture/errors',route=>route.fulfill({json:{errors:[{
    player_id:'P1',callback:'validate_action',phase:'PLAYING',turn_number:1,decision_id:17,
    error:'TRADE missing give, receive and recipients',returned_action:{type:'TRADE'},
    available_types:['TRADE','END_TURN'],hint:'Fill the trade template.',
    traceback:'Traceback (most recent call last):\nValueError: Invalid trade <script>never executed</script>'
  }]}}));
  await page.goto('/#match/game-fixture');
  await page.getByRole('button',{name:'Player error log',exact:true}).click();
  await expect(page.locator('#modalBody')).toContainText('TRADE missing give');
  await expect(page.locator('#modalBody')).toContainText('"type": "TRADE"');
  await expect(page.locator('#modalBody')).toContainText('ValueError: Invalid trade <script>never executed</script>');
  await expect(page.locator('#modalBody script')).toHaveCount(0);
});
async function register(page,name,email){
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByRole('button',{name:'New here? Create an account',exact:true}).click();
  await page.getByRole('textbox',{name:'Display name',exact:true}).fill(name);
  await page.getByRole('textbox',{name:'Email',exact:true}).fill(email);
  await page.getByLabel('Password',{exact:true}).fill('browser-test-password');
  await page.getByRole('button',{name:'Create account',exact:true}).click();
  await expect(page.locator('#accountName')).toHaveText(name);
}
async function uploadBot(page,bot,testAfterSaving=false){
  await page.goto('/#bots');
  await page.getByRole('button',{name:'+ Add player version',exact:true}).click();
  await page.getByRole('textbox',{name:'Player name',exact:true}).fill(bot);
  await page.getByRole('textbox',{name:'Version',exact:true}).fill('v1');
  await page.getByRole('textbox',{name:'Or paste code',exact:true}).fill(playerCode);
  await page.getByRole('button',{name:testAfterSaving?'Save and test your player':'Save player version',exact:true}).click();
  await expect(page.getByRole('heading',{name:bot,exact:true})).toBeVisible();
}
test('watch the sample, scrub, replay independently, and display responsive results',async({page,context})=>{
  test.setTimeout(90000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Run and watch Catan bot matches'})).toBeVisible();
  await page.getByRole('button',{name:'Watch sample match',exact:true}).first().click();
  await expect(page.locator('#timeline')).toBeVisible({timeout:30000});
  await expect(page.locator('[data-tile]')).toHaveCount(19);
  await expect(page.locator('#timeline')).toHaveValue('0');
  await expect(page.locator('#results')).toBeHidden();
  await page.screenshot({path:'test-results/replay-desktop.png',fullPage:true});
  await page.getByRole('button',{name:'Next event',exact:true}).click();
  await expect(page.locator('#timeline')).toHaveValue('1');
  await page.getByRole('button',{name:'Next turn',exact:true}).click();
  await expect(page.locator('#turnBadge')).not.toHaveText('TURN 1');
  await page.getByRole('button',{name:'Previous turn',exact:true}).click();
  await expect(page.locator('#timeline')).toHaveValue('0');
  await page.locator('#timeline').fill('6');
  await expect(page.locator('#position')).toHaveText(/^6 \/ /);
  await page.locator('[data-frame="3"]').click();
  await expect(page.locator('#timeline')).toHaveValue('3');
  await page.getByRole('button',{name:'▶ Play',exact:true}).click();
  await expect(page.locator('#timeline')).not.toHaveValue('3');
  await page.getByRole('button',{name:'Ⅱ Pause',exact:true}).click();
  const paused=await page.locator('#timeline').inputValue();
  await page.waitForTimeout(900);
  await expect(page.locator('#timeline')).toHaveValue(paused);
  await page.getByRole('button',{name:'End',exact:true}).click();
  await expect(page.locator('#results')).toBeVisible();
  await expect(page.locator('#results')).toContainText('Victory');
  await expect(page.getByRole('button',{name:'Next event',exact:true})).toBeDisabled();
  const final=await page.locator('#timeline').inputValue();
  const other=await context.newPage();await other.goto(page.url());
  await expect(other.locator('#timeline')).toHaveValue('0');
  await expect(page.locator('#timeline')).toHaveValue(final);
  await other.close();
  await page.getByRole('button',{name:'Beginning',exact:true}).click();
  await expect(page.locator('#players')).toContainText('0 roads');
  await page.reload();await expect(page.locator('#timeline')).toHaveValue('0');
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'test-results/replay-mobile.png',fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
  await page.getByRole('link',{name:'Matches',exact:true}).click();
  await expect(page.getByRole('button',{name:'Watch sample match',exact:true}).first()).toBeVisible();
  expect(errors).toEqual([]);
});

test('four participants select saved bots, ready up and launch a recorded batch',async({page,browser})=>{
  test.setTimeout(120000);
  const suffix=Date.now().toString(36),bot=`Player-${suffix}`;
  await page.goto('/#bots');await register(page,'Alice',`alice-${suffix}@example.com`);
  await uploadBot(page,bot);
  await page.getByRole('link',{name:'Rooms',exact:true}).click();
  await page.getByRole('button',{name:'+ Create room',exact:true}).click();
  await page.getByRole('textbox',{name:'Room name',exact:true}).fill(`Test table ${suffix}`);
  await page.locator('#roomForm').getByRole('button',{name:'Create room',exact:true}).click();
  await expect(page.locator('[data-seat-bot]')).toBeVisible();
  const url=page.url();
  await page.locator('[data-seat-bot]').selectOption({index:1});
  await page.getByRole('button',{name:'Mark ready',exact:true}).click();
  await expect(page.getByRole('button',{name:'Not ready',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Not ready',exact:true}).click();
  await expect(page.getByRole('button',{name:'Mark ready',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Mark ready',exact:true}).click();
  const contexts=[];
  try{
    for(const who of ['Bob','Carol','Dave']){
      const ctx=await browser.newContext();contexts.push(ctx);const participant=await ctx.newPage();
      await participant.goto(url);await register(participant,who,`${who.toLowerCase()}-${suffix}@example.com`);
      await uploadBot(participant,bot);await participant.goto(url);
      await participant.getByRole('button',{name:'Join this room',exact:true}).first().click();
      await participant.locator('[data-seat-bot]').selectOption({index:1});
      await participant.getByRole('button',{name:'Mark ready',exact:true}).click();
      await expect(participant.getByRole('button',{name:'Not ready',exact:true})).toBeVisible();
    }
    // Changing the lineup clears human readiness; approve the final table.
    for(const participant of [page,...contexts.map(ctx=>ctx.pages()[0])]){
      await participant.goto(url);
      await participant.reload();
      await expect(participant.locator('[data-seat-bot]')).toBeVisible();
      const readyButton=participant.getByRole('button',{name:'Mark ready',exact:true});
      if(await readyButton.isVisible())await readyButton.click();
      await expect(participant.getByRole('button',{name:'Not ready',exact:true})).toBeVisible();
      if(participant===page)await page.getByLabel('Matches',{exact:true}).fill('2');
    }
    // Readiness continues updating while the host is editing the batch count.
    await expect(page.getByRole('button',{name:'Delete room',exact:true})).toHaveCount(0);
    await expect(page.getByRole('button',{name:'Run 2 matches →',exact:true})).toBeEnabled();
    await page.screenshot({path:'test-results/room-ready.png',fullPage:true});
    await page.getByRole('button',{name:'Run 2 matches →',exact:true}).click();
    await expect(page.locator('#timeline')).toBeVisible({timeout:30000});
    await expect(page.getByRole('navigation',{name:'Batch matches'}).locator('a')).toHaveCount(2);
    await expect(page.locator('#players')).toContainText('Alice');
    await expect(page.locator('#players')).toContainText('Dave');
    await expect(page.locator('#players')).toContainText(bot);
    await page.goto(url);
    await expect(page.getByRole('button',{name:'Watch match',exact:true}).first()).toBeVisible();
    await expect(page.locator('.room-history')).toContainText('2 matches');
  }finally{for(const ctx of contexts)await ctx.close();}
});

test('test your player creates a private room with configurable simulation opponents',async({page})=>{
  test.setTimeout(120000);
  const suffix=Date.now().toString(36);
  await page.goto('/');
  await register(page,`Tester-${suffix}`,`tester-${suffix}@example.com`);
  await uploadBot(page,`Test player ${suffix}`);
  await page.getByRole('button',{name:'Test your player',exact:true}).click();
  await page.getByRole('button',{name:'Create private test room',exact:true}).click();
  await expect(page.locator('[data-builtin-seat]')).toHaveCount(3);
  await expect(page.locator('#app')).toContainText('Private room');
  await page.locator('[data-builtin-seat="1"]').selectOption('hard');
  await expect(page.locator('[data-builtin-seat="1"]')).toHaveValue('hard');
  await page.getByRole('button',{name:'Mark ready',exact:true}).click();
  await page.getByRole('button',{name:'Simulate match →',exact:true}).click();
  await expect(page.locator('#timeline')).toBeVisible({timeout:60000});
  await expect(page.locator('#players')).toContainText('Hard bot');
});

test('upload dialog can save and test a player directly',async({page})=>{
  const suffix=Date.now().toString(36);
  await page.goto('/');
  await register(page,`UploadTester-${suffix}`,`upload-${suffix}@example.com`);
  await uploadBot(page,`Upload test ${suffix}`,true);
  await expect(page.getByRole('button',{name:'Create private test room',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Create private test room',exact:true}).click();
  await expect(page.locator('[data-builtin-seat]')).toHaveCount(3);
});

test('user names are rendered as text, and missing matches have a recoverable error',async({page,request})=>{
  const bot=`<img src=x onerror=alert(1)>-${Date.now()}`;
  await request.post('/bots/upload',{data:{bot_name:bot,bot_version:'v1',use_sandbox:true,bot_code:playerCode}});
  let alert=false;page.on('dialog',async d=>{alert=true;await d.dismiss();});
  await page.goto('/#bots');
  await expect(page.getByRole('heading',{name:bot,exact:true})).toBeVisible();
  expect(await page.locator('.card img').count()).toBe(0);expect(alert).toBe(false);
  await page.goto('/#match/game-missing');
  await expect(page.getByRole('heading',{name:'Could not load this page'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Try again'})).toBeVisible();
});

test('rooms continue refreshing without treating the room list as a function',async({page})=>{
  await page.goto('/#rooms');
  await expect(page.getByRole('heading',{name:'Rooms',exact:true})).toBeVisible();
  await page.waitForTimeout(2500);
  await expect(page.locator('#notice')).toBeHidden();
  await expect(page.getByRole('heading',{name:'Rooms',exact:true})).toBeVisible();
});

test('complete geometry contract renders roads, cities, ports and reversible positions',async({page})=>{
  const {metadata,replay}=completeBoardFixture();
  expect(replay.geometry.vertices).toHaveLength(54);
  expect(replay.geometry.edges).toHaveLength(72);
  expect(replay.geometry.ports).toHaveLength(9);
  await page.route('**/games/game-fixture',route=>route.fulfill({json:metadata}));
  await page.route('**/game/game-fixture/replay',route=>route.fulfill({json:replay}));
  await page.goto('/#match/game-fixture');
  await expect(page.locator('[data-tile]')).toHaveCount(19);
  await expect(page.locator('#topology')).toBeHidden();
  await page.getByRole('button',{name:'Next event',exact:true}).click();
  await expect(page.locator('#feed')).toContainText('Ada gave 2 wood to Babbage for 1 ore');
  await expect(page.locator('#players')).toContainText('1 cities');
  await expect(page.locator('#board line[stroke-width="7"]')).toHaveCount(4);
  await expect(page.locator('#board text').filter({hasText:/3:1|2:1/})).toHaveCount(9);
  await page.screenshot({path:'test-results/complete-geometry-fixture.png',fullPage:true});
  await page.getByRole('button',{name:'Previous event',exact:true}).click();
  await expect(page.locator('#board line[stroke-width="7"]')).toHaveCount(0);
  await expect(page.locator('#players')).toContainText('0 cities');
});
