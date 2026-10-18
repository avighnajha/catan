import {test} from 'node:test';
import assert from 'node:assert/strict';
import {validationMarkup} from '../src/platform/static/validation.js';

test('validation stages display progress, failures and escaped private diagnostics',()=>{
  const html=validationMarkup({stages:{
    quick:{status:'passed',message:'Loaded'},
    scenarios:{status:'failed',message:'Invalid action',details:{error:'<script>bad()</script>',returned_action:{type:'TRADE'},traceback:'ValueError: <secret>',available_types:['TRADE','END_TURN']}},
    games:{status:'skipped',message:'Not run'}
  }});
  assert.match(html,/Quick checks/);assert.match(html,/Scenario checks/);assert.match(html,/Full game checks/);
  assert.match(html,/Passed/);assert.match(html,/Not run/);assert.match(html,/&lt;script&gt;/);
  assert.ok(!html.includes('<script>'));assert.match(html,/Returned action/);assert.match(html,/Stack trace/);
});
