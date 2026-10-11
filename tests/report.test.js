import test from 'node:test';
import assert from 'node:assert/strict';
import {developmentCards,resourceHistory} from '../src/platform/static/report.js';

test('counts played public cards once, per seat, excluding purchases and victory points',()=>{
  const events=[
    {type:'DevelopmentCardPlayed',player_id:'P1',data:{card:'KNIGHT'}},
    {type:'DevelopmentCardPlayed',player_id:'P1',data:{card:'KNIGHT'}},
    {type:'DevelopmentCardPlayed',player_id:'P1',data:{card:'ROAD_BUILDING'}},
    {type:'DevelopmentCardPlayed',player_id:'P2',data:{card:'MONOPOLY'}},
    {type:'DevelopmentCardPurchased',player_id:'P1',data:{card:'KNIGHT'}},
    {type:'DevelopmentCardPlayed',player_id:'P1',data:{card:'VICTORY_POINT'}}
  ];
  const replay={events,frames:[{events}]};
  assert.deepEqual(developmentCards(replay,'P1'),{total:3,counts:{KNIGHT:2,ROAD_BUILDING:1,YEAR_OF_PLENTY:0,MONOPOLY:0}});
  assert.equal(developmentCards(replay,'P2').total,1);
  assert.equal(developmentCards(replay,'P3').total,0);
  assert.equal(developmentCards({frames:[{events}]},'P1').total,3);
});

test('resource history retains within-turn changes, setup and final partial turn',()=>{
  const frames=[['SETUP_FIRST',1,0],['SETUP_SECOND',1,1],['NORMAL_PLAY',1,2],['NORMAL_PLAY',1,5],['NORMAL_PLAY',1,1],['GAME_OVER',2,3]].map(([phase,turn_number,wood],sequence)=>({
    sequence,label:`position ${sequence}`,state:{phase,turn_number,players:[{player_id:'P1',resources:{WOOD:wood}},{player_id:'P2',resources:{ORE:9}}]}
  }));
  const points=resourceHistory({frames},'P1');
  assert.deepEqual(points.map(p=>p.resources.WOOD),[0,1,2,5,1,3]);
  assert.deepEqual(points.map(p=>p.turn),[0,0,1,1,1,2]);
  assert.deepEqual(points.map(p=>p.x),[0,.5,1,1+1/3,1+2/3,2]);
  assert.ok(points.every(p=>p.resources.ORE===0));
  assert.ok(resourceHistory({frames},'P2').every(p=>p.resources.ORE===9));
  assert.deepEqual(resourceHistory({frames:[{state:{phase:'GAME_OVER',players:[{player_id:'P1'}]}}]},'P1'),[]);
  assert.deepEqual(resourceHistory({frames:[frames[0],{...frames[0],state:{...frames[0].state,phase:'GAME_OVER'}}]},'P1').map(p=>p.turn),[0,0]);
});
