'use strict';
const assert=require('node:assert/strict');const {createVoiceBridge}=require('./bridge.js');
async function scenario(stale=false){
 let active=true,pending={clarify_id:'question-1',question:'Which city?',choices:['Brooklyn','Boston']},posts=0,responses=[],feedback=[],done=false,answer;
 const b=createVoiceBridge({target:()=>({sid:'A'}),sameTarget:()=>true,offer:()=>{},status:()=>{},attach:()=>{},wait:()=>new Promise(r=>setTimeout(r,5)),feedback:t=>feedback.push(t),result:async t=>{answer=t;done=true;return {sent:true};},api:async(p,o)=>{
 if(p==='/api/chat/start'){posts++;return {stream_id:'run'};}
 if(p.startsWith('/api/clarify/pending'))return {pending};
 if(p==='/api/clarify/respond'){const data=JSON.parse(o.body);assert.equal(data.clarify_id,'question-1');assert.equal(data.session_id,'A');responses.push(data.response);pending=null;active=false;return {ok:true};}
 if(p.includes('stream/status'))return {active,stream_id:'run',task_outcome:{status:'succeeded'}};
 return {session:{messages:posts?[{role:'assistant',content:'Brooklyn selected'}]:[]}};
 }});
 await b.route('Ask me which city before answering.','initial');
 for(let i=0;i<100&&!feedback.some(x=>x.includes('Which city?'));i++)await new Promise(r=>setTimeout(r,5));
 assert.equal(feedback.filter(x=>x.includes('Which city?')).length,1);
 if(stale){pending=null;assert.equal((await b.route('Brooklyn','reply')).accepted,false);assert.equal(responses.length,0);active=false;}
 else{assert.equal((await b.route('Brooklyn','reply')).accepted,true);assert.deepEqual(responses,['Brooklyn']);await b.route('Brooklyn','reply');assert.equal(responses.length,1);}
 for(let i=0;i<100&&!done;i++)await new Promise(r=>setTimeout(r,5));
 assert.equal(answer,'Brooklyn selected');assert.equal(posts,1);
}
(async()=>{await scenario();await scenario(true);console.log('PASS question relayed once, exact-id answer/readback, same run continued, duplicate and stale answer blocked');})().catch(e=>{console.error(e);process.exitCode=1;});
