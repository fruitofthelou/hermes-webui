'use strict';
const assert=require('node:assert/strict');
const {createVoiceBridge}=require('./bridge.js');
(async()=>{
 let posts=0,results=[],attached=0,mode='ok',bridge;
 const target={sid:'test',profile:'default'};
 const deps={target:()=>target,sameTarget:()=>mode!=='switch',offer:()=>{},status:()=>{},attach:()=>attached++,wait:async()=>{if(mode==='stop')bridge.reset();},result:(text,id)=>results.push({text,id}),api:async(p,o)=>{
  if(p==='/api/chat/start'){posts++;return {stream_id:'run'};}
  if(p.startsWith('/api/chat/stream/status'))return {active:false,stream_id:'run',task_outcome:{status:'succeeded'}};
  return {session:{model:'test',model_provider:'test',messages:posts?[{role:'user',content:'hello'},{role:'assistant',content:'hidden',tool_calls:[{}]},{role:'tool',content:'secret'},{role:'assistant',content:'Actual answer'}]:[]}};
 }};
 bridge=createVoiceBridge(deps);bridge.offer('hello','d1');assert.equal(posts,0);
 await Promise.all([bridge.confirm(),bridge.confirm()]);assert.equal(posts,1);assert.deepEqual(results,[{text:'Actual answer',id:'d1'}]);assert.equal(attached,1);
 bridge.offer('duplicate','d1');await bridge.confirm();assert.equal(posts,1);
 for(const m of ['stop','switch']){posts=0;results=[];mode=m;bridge=createVoiceBridge(deps);bridge.offer('hello');await bridge.confirm();assert.equal(results.length,0);}
 console.log('PASS confirmation, exactly-once click, duplicate delegation, final-answer filtering, Stop and session-switch detachment');
})();
