'use strict';
const assert=require('node:assert/strict');const {createVoiceBridge}=require('./bridge.js');
async function scenario(mode){
 let active=true,posts=0,delivered=0,cancels=0,approval=mode==='approval'?{id:'p1',command:'SECRET MUST NOT BE SPOKEN'}:null;const feedback=[],history=[];
 const b=createVoiceBridge({target:()=>({sid:'A'}),sameTarget:()=>true,offer:()=>{},status:()=>{},attach:()=>{},wait:()=>new Promise(r=>setTimeout(r,5)),queue:s=>{history.splice(0,history.length,...s.history)},feedback:s=>feedback.push(s),result:async()=>{delivered++;return {sent:true}},api:async(p,o)=>{
 if(p==='/api/chat/start'){posts++;return {stream_id:'run'}};
 if(p.includes('/approval/pending'))return {pending:approval};
 if(p.includes('/clarify/pending'))return {pending:null};
 if(p.includes('stream/status'))return {active,stream_id:'run',task_outcome:{status:'succeeded'},unconsumed_steering:mode==='leftover'?true:mode==='unknown'?undefined:false};
 if(p==='/api/chat/steer')return {accepted:true,stream_id:'run'};
 if(p.includes('/cancel?')){cancels++;active=false;return {cancelled:true}};
 return {session:{messages:posts?[...(mode==='consumed'?[{role:'user',content:'Change the city to Brooklyn'}]:[]),{role:'assistant',content:'Final answer'}]:[]}};
 }});
 await b.route('Initial task','start');await new Promise(r=>setTimeout(r,30));
 if(mode==='approval'){
 assert.equal(feedback.filter(s=>s.includes('permission to run')).length,1);assert.ok(!feedback.join('').includes('SECRET'));
 assert.equal((await b.route('yes','yes')).reason,'approval_pending');assert.equal(posts,1);assert.equal(cancels,0);
 assert.equal((await b.route('Cancel the task.','cancel')).accepted,true);
 }else{assert.equal((await b.route('Change the city to Brooklyn','update')).accepted,true);active=false;}
 for(let i=0;i<100&&!history.length;i++)await new Promise(r=>setTimeout(r,5));
 assert.equal(posts,1);
 if(mode==='leftover'||mode==='unknown'){assert.equal(delivered,0);assert.equal(history[0].state,'Correction unconfirmed');assert.ok(feedback.some(s=>s.includes('withholding')))}
 if(mode==='consumed'){assert.equal(delivered,1);assert.equal(history[0].state,'Completed')}
 if(mode==='approval'){assert.equal(cancels,1);assert.equal(delivered,0);assert.ok(feedback.some(s=>s.includes('no longer active')))}
}
(async()=>{for(const mode of ['leftover','unknown','consumed','approval'])await scenario(mode);console.log('PASS leftover/unknown steering withholds stale answers; consumed update delivers; approval notice once/no secrets; spoken yes blocked; exact cancellation during approval verified inactive');})().catch(e=>{console.error(e);process.exitCode=1});
