'use strict';
const assert=require('node:assert/strict');
const {createVoiceBridge}=require('./bridge.js');
async function scenario(delivery,expected){
 let starts=0,history=[],state,queueState,release;const audits=[];
 const gate=new Promise(r=>release=r);
 const bridge=createVoiceBridge({target:()=>({sid:'A',profile:'default'}),sameTarget:()=>true,
  queue:s=>{history=s.history;queueState=s;},state:s=>state=s,offer(){},status(){},attach(){},audit:(k,f)=>audits.push([k,f]),
  wait:async()=>gate,result:async()=>delivery,
  api:async p=>p==='/api/chat/start'?(starts++,{stream_id:'owned'}):p.includes('stream/status')?{active:false,stream_id:'owned',task_outcome:{status:'succeeded'}}:p.includes('/api/session')?{session:{messages:Array.from({length:starts},()=>({role:'assistant',content:'Brooklyn forecast.'})),model:'m'}}:{pending:null}});
 bridge.offer('Forecast','first');const work=bridge.confirm();await new Promise(r=>setImmediate(r));
 bridge.offer('Independent next request','second');await bridge.confirm();release();await work;
 const first=history.find(r=>r.id==='first');assert.equal(first.state,expected,'delivery uncertainty is not backend failure');
 assert.equal(first.backendOutcome.status,'succeeded');assert.equal(first.delivery.audibleConfirmed,null,'never infer hearing');
 assert.equal(state.lastFailed,null);assert.equal(state.lastAnswer,'Brooklyn forecast.');
 assert.equal(audits.filter(([k])=>k==='task_failure').length,0);
 if(expected==='Delivery unconfirmed'||expected==='Failed'){
  assert.equal(starts,1);assert.equal(queueState.paused,true);assert.equal(queueState.waiting.length,1);
  assert.equal(state.waiting.length,1);assert.equal(first.delivery.reason,delivery.reason);
  if(expected==='Delivery unconfirmed'){assert.equal(first.delivery.providerFailed,false);assert.equal(first.delivery.receiptConfirmed,false);}
  assert.equal((await bridge.control('steer','change')).accepted,false);
 }else assert.equal(starts,2);
 bridge.reset();assert.equal(queueState.waiting.length,0);assert.equal(queueState.paused,false);
}
(async()=>{
 for(const reason of ['missing_receipt','output_timeout','turn_completion_timeout','end_call','connection_closed','channel_unavailable','send_failed'])
  await scenario({sent:false,reason,providerTurnComplete:reason==='missing_receipt',receiptConfirmed:false},'Delivery unconfirmed');
 await scenario({sent:false,reason:'quota',providerFailed:true},'Failed');
 await scenario({sent:false,interrupted:true,reason:'user_interruption'},'Interrupted');
 await scenario({sent:true,providerTurnComplete:true,receiptConfirmed:true},'Completed');
 console.log('PASS delivery classification, independent backend/turn/receipt/audible facts, paused FIFO and no automatic retry');
})().catch(e=>{console.error(e);process.exitCode=1;});
