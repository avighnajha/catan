// Match analysis uses finished spectator recordings, never player observations.
export const resources=[['WOOD','Wood','#326b45'],['BRICK','Brick','#b24f36'],['SHEEP','Sheep','#7d8d24'],['WHEAT','Wheat','#ba820f'],['ORE','Ore','#526d9a']];
const cards=[['KNIGHT','Knight'],['ROAD_BUILDING','Road building'],['YEAR_OF_PLENTY','Year of plenty'],['MONOPOLY','Monopoly']];
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function developmentCards(replay,playerId){
  const counts=Object.fromEntries(cards.map(([key])=>[key,0]));
  const events=replay.events?.length?replay.events:(replay.frames||[]).flatMap(frame=>frame.events||[]);
  for(const event of events)if(event.type==='DevelopmentCardPlayed'&&event.player_id===playerId&&Object.hasOwn(counts,event.data?.card))counts[event.data.card]++;
  return {counts,total:Object.values(counts).reduce((a,b)=>a+b,0)};
}

export function resourceHistory(replay,playerId){
  const points=[];
  let setup=false;
  for(const [index,frame] of (replay.frames||[]).entries()){
    if(frame.state.phase.startsWith('SETUP'))setup=true;
    else if(frame.state.phase==='NORMAL_PLAY')setup=false;
    const player=frame.state.players.find(p=>p.player_id===playerId);
    if(!player?.resources)continue; // Older recordings may not contain hands.
    points.push({frame:index,label:frame.label,turn:setup?0:frame.state.turn_number,
                 resources:Object.fromEntries(resources.map(([key])=>[key,player.resources[key]||0]))});
  }
  // Equal-width turn intervals, with every transition ordered inside its turn.
  for(let start=0;start<points.length;){
    let end=start+1;while(end<points.length&&points[end].turn===points[start].turn)end++;
    for(let i=start;i<end;i++)points[i].x=points[i].turn+(i-start)/(end-start);
    start=end;
  }
  return points;
}

export function developmentCardReport(replay,participants){
  return `<div class="card report-card"><h3>Development cards played</h3><p class="muted">Select a player to see counts by card type. Victory point cards are excluded.</p><div class="dev-card-list">${participants.map(p=>{
    const {counts,total}=developmentCards(replay,p.player_id);
    return `<details><summary>${escape(p.name||p.player_id)} <strong>${total} played</strong></summary><dl>${cards.map(([key,label])=>`<div><dt>${label}</dt><dd>${counts[key]}</dd></div>`).join('')}</dl></details>`;
  }).join('')}</div></div>`;
}

export function mountResourceReport(container,replay,participants){
  container.innerHTML=`<h3>Resources held over time</h3><p class="muted">Select a player to see their resources during the match. Opponent resource counts are only shown in finished replays.</p><div class="resource-tabs" role="tablist" aria-label="Player resource histories">${participants.map((p,i)=>`<button role="tab" id="resource-tab-${i}" aria-controls="resource-chart-panel" aria-selected="${i===0}" tabindex="${i===0?0:-1}">${escape(p.name||p.player_id)}</button>`).join('')}</div><div id="resource-chart-panel" role="tabpanel" aria-labelledby="resource-tab-0"></div>`;
  const tabs=[...container.querySelectorAll('[role=tab]')],panel=container.querySelector('[role=tabpanel]');
  function select(index){
    tabs.forEach((tab,i)=>{tab.setAttribute('aria-selected',String(i===index));tab.tabIndex=i===index?0:-1;});
    panel.setAttribute('aria-labelledby',tabs[index].id);
    drawResourceChart(panel,resourceHistory(replay,participants[index].player_id),participants[index].name||participants[index].player_id);
  }
  tabs.forEach((tab,i)=>{
    tab.onclick=()=>select(i);
    tab.onkeydown=event=>{let next;if(event.key==='ArrowRight')next=(i+1)%tabs.length;else if(event.key==='ArrowLeft')next=(i+tabs.length-1)%tabs.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;else return;event.preventDefault();select(next);tabs[next].focus();};
  });
  if(tabs.length)select(0);
}

function drawResourceChart(panel,points,name){
  if(!points.length){panel.innerHTML='<p class="muted">Resource history is unavailable in this older recording.</p>';return;}
  const width=900,height=280,left=42,right=18,top=16,bottom=40;
  const maxX=Math.max(1,points.at(-1).x),maxY=points.reduce((max,p)=>Math.max(max,...Object.values(p.resources)),1);
  const x=value=>left+value/maxX*(width-left-right),y=value=>height-bottom-value/maxY*(height-top-bottom);
  const yStep=Math.max(1,Math.ceil(maxY/5)),yTicks=Array.from({length:Math.floor(maxY/yStep)+1},(_,i)=>i*yStep);
  const turnStep=Math.max(1,Math.ceil(maxX/10)),turnTicks=Array.from({length:Math.floor(maxX/turnStep)+1},(_,i)=>i*turnStep);
  panel.innerHTML=`<fieldset class="resource-legend"><legend class="sr-only">Visible resource lines</legend>${resources.map(([key,label,color])=>`<label style="--resource-color:${color}"><input type="checkbox" checked data-resource="${key}"><span></span>${label}</label>`).join('')}</fieldset><div class="chart-scroll"><svg class="resource-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escape(name)} resource cards held throughout the match"><title>${escape(name)} resource history. Use the slider below to inspect exact counts.</title>${yTicks.map(n=>`<line class="chart-grid" x1="${left}" x2="${width-right}" y1="${y(n)}" y2="${y(n)}"/><text x="${left-8}" y="${y(n)+4}" text-anchor="end">${n}</text>`).join('')}${turnTicks.map(n=>`<text x="${x(n)}" y="${height-bottom+20}" text-anchor="middle">${n===0?'Setup':n}</text>`).join('')}<text x="${width/2}" y="${height-2}" text-anchor="middle">Turn (each player's turn)</text>${resources.map(([key,,color],i)=>{
    const d=points.map((point,j)=>`${j?'H':'M'} ${x(point.x).toFixed(2)}${j?' V':' '}${y(point.resources[key]).toFixed(2)}`).join(' ');
    return `<path data-series="${key}" d="${d}" fill="none" stroke="${color}" stroke-width="2.5" ${i?`stroke-dasharray="${[0,'8 3','3 3','12 3 3 3','2 5'][i]}"`:''}/>`;
  }).join('')}<line class="chart-cursor" y1="${top}" y2="${height-bottom}"/></svg></div><label class="chart-slider">Inspect recorded position<input type="range" min="0" max="${points.length-1}" value="${points.length-1}" step="1" aria-label="Resource history position"></label><p class="chart-position"></p><div class="chart-counts" aria-live="polite"></div>`;
  const slider=panel.querySelector('input[type=range]'),svg=panel.querySelector('svg'),cursor=panel.querySelector('.chart-cursor');
  function inspect(index){
    const point=points[index];slider.value=index;
    cursor.setAttribute('x1',x(point.x));cursor.setAttribute('x2',x(point.x));
    const label=`${point.turn===0?'Setup':`Turn ${point.turn}`} · ${point.label} · recorded position ${point.frame}`;
    panel.querySelector('.chart-position').textContent=label;slider.setAttribute('aria-valuetext',label);
    panel.querySelector('.chart-counts').innerHTML=resources.map(([key,label,color])=>`<span style="--resource-color:${color}"><i></i>${label} <strong>${point.resources[key]}</strong></span>`).join('');
  }
  slider.oninput=()=>inspect(Number(slider.value));
  svg.onpointermove=event=>{const box=svg.getBoundingClientRect(),target=((event.clientX-box.left)/box.width*width-left)/(width-left-right)*maxX;let closest=0;for(let i=1;i<points.length;i++)if(Math.abs(points[i].x-target)<Math.abs(points[closest].x-target))closest=i;inspect(closest);};
  panel.querySelectorAll('[data-resource]').forEach(input=>input.onchange=()=>{panel.querySelector(`[data-series="${input.dataset.resource}"]`).style.display=input.checked?'':'none';});
  inspect(points.length-1);
}
