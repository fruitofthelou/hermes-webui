'use strict';
const assert=require('node:assert/strict');
const {createVoiceBridge}=require('./bridge.js');
async function scenario(code,{hang=null,marked=false,missing=false,mismatch=false}={}){
  let release,starts=0,submitted=[],state,history=[],spoken=[],notices=[],audits=[],polls=0;
  const gate=new Promise(r=>release=r);
  const b=createVoiceBridge({apiTimeoutMs:15,target:()=>({sid:'A',profile:'default'}),sameTarget:()=>true,
    state:s=>state=s,queue:s=>history=s.history,offer:()=>{},status:()=>{},feedback:t=>notices.push(t),attach:()=>{},
    wait:async()=>gate,result:async t=>{spoken.push(t);return {sent:true};},audit:(k,f)=>audits.push([k,f]),
    api:async(p,o)=>{
      if(p==='/api/chat/start'){starts++;submitted.push(JSON.parse(o.body));if(hang==='submit')return new Promise(()=>{});return {stream_id:'owned'};}
      if(p.includes('stream/status')){polls++;if(hang==='poll')return new Promise(()=>{});return {active:false,stream_id:mismatch?'foreign':'owned',task_outcome:missing?undefined:{status:code?'failed':'succeeded',code,stage:'terminal_journal',event_id:'owned:2'}};}
      if(p.includes('/api/session'))return {session:{messages:Array.from({length:starts},()=>({role:'assistant',content:code?'DO NOT SPEAK PROVIDER SECRET':'A normal explanation about quota and rate limits',_error:marked})),model:'m'}};
      return {pending:null};
    }});
  b.remember('user','original conversation');b.offer('Explain weather and climate','first');const work=b.confirm();await new Promise(r=>setImmediate(r));
  b.offer('Unstarted queued request','second');await b.confirm();release();await work;
  const failed=!!code||hang||marked||missing||mismatch;
  assert.equal(starts,failed?1:2,'failed run must never dispatch unstarted queue');
  if(failed){
    assert.equal(spoken.length,0);assert.ok(history.some(r=>r.state==='Failed'));assert.ok(history.some(r=>r.state==='Removed'));
    assert.equal(state.running,null);assert.deepEqual(state.waiting,[]);assert.equal(state.lastAnswer,null);
    assert.equal(state.lastFailed.text,'Explain weather and climate');assert.equal(state.lastFailed.context[0].text,'original conversation');
    assert.equal(state.lastFailed.streamId,hang==='submit'?null:'owned');
    if(hang)assert.equal(state.lastFailed.outcome,'unconfirmed');
    assert.equal(audits.filter(([k])=>k==='task_failure').length,1);assert.equal(audits.filter(([k])=>k==='hermes_answer').length,0);
    assert.ok(notices.at(-1).includes('only if you ask'));assert.ok(!notices.join(' ').includes('PROVIDER SECRET'));
    assert.ok(!JSON.stringify(audits).includes('PROVIDER SECRET'));
    if(!hang){b.offer('I fixed the issue; try that request again','retry');await b.confirm();assert.equal(starts,2);assert.ok(submitted[1].message.includes('Explain weather and climate'));assert.ok(submitted[1].message.includes('lastFailed'));}
    b.reset();assert.equal(state.lastFailed,null);
  }else assert.equal(spoken.length,2,'normal answer mentioning errors is not classified as failure');
}
(async()=>{
  for(const code of ['quota_exhausted','rate_limit','policy_blocked','auth_mismatch','model_not_found','timeout','backend_error','credential_pool_empty','no_response','cancelled'])await scenario(code);
  await scenario(null,{hang:'submit'});await scenario(null,{hang:'poll'});await scenario(null,{marked:true});await scenario(null,{missing:true});await scenario(null,{mismatch:true});await scenario(null);
  console.log('PASS structured task failure: categories, queued cleanup, safe notices, retained context, authorized retry, API hangs, unknown/mismatched outcome, marked errors and successful prose');
})().catch(e=>{console.error(e);process.exitCode=1;});
