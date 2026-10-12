const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const timestamp=game=>Number.isFinite(Date.parse(game.created_at))?Date.parse(game.created_at):0;

export function groupMatches(games){
  const batches=new Map();
  for(const game of games){
    const key=JSON.stringify(game.batch_id?[game.room_id,game.batch_id]:[game.game_id]);
    if(!batches.has(key))batches.set(key,{key,matches:[]});
    batches.get(key).matches.push(game);
  }
  const days=new Map();
  const sorted=[...batches.values()].map(batch=>{
    batch.matches.sort((a,b)=>(a.batch_index||1)-(b.batch_index||1)||timestamp(a)-timestamp(b));
    batch.startedAt=Math.min(...batch.matches.map(timestamp));
    return batch;
  }).sort((a,b)=>b.startedAt-a.startedAt||a.key.localeCompare(b.key));
  for(const batch of sorted){
    const date=new Date(batch.startedAt),key=batch.startedAt?`${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`:'unknown';
    if(!days.has(key))days.set(key,{key,date:batch.startedAt?date:null,batches:[],count:0});
    const day=days.get(key);day.batches.push(batch);day.count+=batch.matches.length;
  }
  return [...days.values()];
}

export function matchArchive(games,{view,openStates,card}){
  if(view==='all')return `<div class="cards">${[...games].sort((a,b)=>timestamp(b)-timestamp(a)).map(card).join('')}</div>`;
  return groupMatches(games).map((day,index)=>{
    const dayKey=`date-${day.key}`;
    const label=day.date?day.date.toLocaleDateString('en-GB',{day:'numeric',month:'short',...(day.date.getFullYear()!==new Date().getFullYear()?{year:'numeric'}:{})}):'Unknown date';
    return `<details class="archive-date" data-archive-key="${esc(dayKey)}" ${(openStates.get(dayKey)??index===0)?'open':''}><summary><h3>${esc(label)}</h3><span class="count">${day.count} ${day.count===1?'match':'matches'}</span></summary><div class="archive-batches">${day.batches.map(batch=>{
      const game=batch.matches[0],batchKey=`batch-${batch.key}`,finished=batch.matches.filter(g=>!['queued','running'].includes(g.status)).length;
      const title=game.batch_id?`Batch ${game.batch_number||'—'}`:'Single match';
      const time=batch.startedAt?new Date(batch.startedAt).toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'}):'Time unavailable';
      return `<details class="card archive-batch" data-archive-key="${esc(batchKey)}" ${openStates.get(batchKey)?'open':''}><summary><span class="archive-batch-title">${esc(title)} <span class="muted">· ${esc(game.room_name||'Recorded match')}</span></span><span class="muted archive-batch-info">${esc(time)} · ${batch.matches.length} ${batch.matches.length===1?'match':'matches'} · ${finished} finished</span><span class="muted archive-batch-players">${esc((game.players||[]).join(' · '))}</span></summary><div class="cards">${batch.matches.map(card).join('')}</div></details>`;
    }).join('')}</div></details>`;
  }).join('');
}
