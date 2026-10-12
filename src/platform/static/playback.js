/** Pure playback navigation, independent of the DOM and simulator rules. */
export function turnMarkers(frames,width){
  const turns=[];
  frames.forEach((frame,index)=>{
    const turn=frame.state.turn_number;
    if(!turns.length||turn!==turns.at(-1).turn)turns.push({turn,index,position:index/(frames.length-1||1)});
  });
  if(turns.length<2)return turns;
  // Leave room for the longest label and a gap, including on narrow screens.
  const gap=Math.max(40,...turns.map(({turn})=>String(turn).length*7+16));
  const first=turns[0],last=turns.at(-1),selected=[first];
  for(const marker of turns.slice(1,-1)){
    if((marker.position-selected.at(-1).position)*width>=gap&&(last.position-marker.position)*width>=gap)selected.push(marker);
  }
  if((last.position-selected.at(-1).position)*width>=gap)selected.push(last);
  return selected;
}

export class Playback {
  constructor(frames){this.frames=frames;this.index=0;}
  seek(index){this.index=Math.max(0,Math.min(this.frames.length-1,Number(index)||0));return this.frames[this.index];}
  step(direction){return this.seek(this.index+direction);}
  turn(direction){
    const current=this.frames[this.index].state.turn_number;
    if(direction>0){const next=this.frames.findIndex((f,i)=>i>this.index&&f.state.turn_number!==current);return this.seek(next<0?this.frames.length-1:next);}
    for(let i=this.index-1;i>=0;i--)if(this.frames[i].state.turn_number!==current){const previous=this.frames[i].state.turn_number;while(i>0&&this.frames[i-1].state.turn_number===previous)i--;return this.seek(i);}
    return this.seek(0);
  }
  get atEnd(){return this.index===this.frames.length-1;}
}
