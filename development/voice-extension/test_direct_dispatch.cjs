'use strict';
const assert=require('node:assert/strict');
const {createVoiceBridge,parseLiveAction}=require('./bridge.js');
const payload=(action,text='')=>JSON.stringify({v:1,action,text});
(async()=>{
 for(const bad of ['','{broken','{}','{"v":1,"action":"exec","text":"x"}','{"v":1,"action":"queue","text":""}','{"v":1,"action":"stop","text":"x","extra":true}'])assert.throws(()=>parseLiveAction(bad));
 assert.equal(parseLiveAction(payload('status')).action,'status');assert.equal(parseLiveAction('Ask Hermes to reply with exactly the hands-free request worked').action,'handoff');
 let release,starts=0,active=true,receipts=[],states=[],history=[],delivered=[];
 const gate=new Promise(r=>release=r);
 const bridge=createVoiceBridge({target:()=>({sid:'A',profile:'default'}),sameTarget:()=>true,
 decide:()=>{throw Error('SECOND MODEL MUST NEVER RUN');},offer:()=>{},status:()=>{},feedback:x=>receipts.push(x),state:x=>states.push(x),queue:x=>history=x.history,attach:()=>{},wait:()=>gate,result:async(text)=>{delivered.push(text);return {sent:true};},api:async(p,o)=>{
 if(p==='/api/chat/start'){starts++;assert.ok(JSON.parse(o.body).message.includes('the hands-free request worked'));return {stream_id:'owned'};}
 if(p.includes('stream/status'))return {active,stream_id:'owned',task_outcome:{status:'succeeded'},unconsumed_steering:false};
 if(p==='/api/chat/steer')return {accepted:true,stream_id:'owned'};
 return {session:{messages:starts?[{role:'user',content:'Keep the exact phrase'},{role:'assistant',content:'the hands-free request worked'}]:[],model:'m'}};
 }});
 await bridge.route('Reply exactly: the hands-free request worked','same');await new Promise(r=>setImmediate(r));
 assert.equal(starts,1);assert.ok(receipts.some(x=>x.includes('started its run')));
 await bridge.route('Reply exactly: the hands-free request worked','same');assert.equal(starts,1);
 assert.equal((await bridge.route('Keep the exact phrase','correction')).accepted,true);
 await bridge.route(payload('status'),'status');assert.equal(starts,1);
 active=false;release();await new Promise(r=>setImmediate(r));
 assert.equal(delivered[0],'the hands-free request worked');assert.equal(history[0].state,'Completed');
 assert.equal((await bridge.route(payload('steer','too late'),'late')).accepted,false);assert.equal(starts,1);
 const missing=createVoiceBridge({target:()=>null,feedback:()=>{}});await assert.rejects(missing.route(payload('queue','x'),'x'),/no-chat-target/);
 // End call while pre-submit session lookup is in flight: no late task creation.
 let lookupRelease,lateStarts=0;const lookup=new Promise(r=>lookupRelease=r);
 const stale=createVoiceBridge({target:()=>({sid:'A'}),sameTarget:()=>true,offer:()=>{},status:()=>{},queue:()=>{},api:async p=>{if(p==='/api/chat/start'){lateStarts++;return {stream_id:'late'};}await lookup;return {session:{messages:[]}};}});
 await stale.route(payload('queue','x'),'end-call');stale.reset('end_call');lookupRelease();await new Promise(r=>setImmediate(r));assert.equal(lateStarts,0);
 console.log('PASS direct JSON validation, no classifier invocation, exact answer delivery, deduplication, steer/status, late-control rejection, missing target, end-call pre-submit invalidation');
})().catch(e=>{console.error(e);process.exitCode=1;});
