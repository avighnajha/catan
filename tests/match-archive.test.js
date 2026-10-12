import test from 'node:test';
import assert from 'node:assert/strict';
import {groupMatches} from '../src/platform/static/match-archive.js';

test('archive groups by batch identity, keeps batches across midnight together, and orders their matches',()=>{
  const games=[
    {game_id:'second',room_id:'A',batch_id:'batch',batch_index:2,created_at:'2026-01-13T00:01:00'},
    {game_id:'other-room',room_id:'B',batch_id:'batch',batch_index:1,created_at:'2026-01-12T13:00:00'},
    {game_id:'first',room_id:'A',batch_id:'batch',batch_index:1,created_at:'2026-01-12T23:59:00'},
    {game_id:'legacy',room_id:'A',created_at:'2026-01-10T12:00:00'}
  ];
  const days=groupMatches(games);
  assert.deepEqual(days.map(day=>[day.key,day.count]),[['2026-01-12',3],['2026-01-10',1]]);
  assert.deepEqual(days[0].batches.map(batch=>batch.matches.map(game=>game.game_id)),[['first','second'],['other-room']]);
  assert.deepEqual(games.map(game=>game.game_id),['second','other-room','first','legacy']);
});

test('recordings without batch metadata remain separate and missing dates have a fallback',()=>{
  const days=groupMatches([{game_id:'old-1',room_id:'same'}, {game_id:'old-2',room_id:'same'}]);
  assert.equal(days.length,1);assert.equal(days[0].date,null);
  assert.equal(days[0].batches.length,2);assert.equal(days[0].count,2);
  assert.deepEqual(groupMatches([]),[]);
});
