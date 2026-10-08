'use strict';
const assert=require('node:assert/strict');const {createVoiceBridge}=require('./bridge.js');
async function scenario(mode){let posts=0,results=0,blocked=0,status=[],cancelCalls=0;let release;
 const pause=new Promise(r=>release=r);let polls=0;
 const target={sid:'A',profile:'default',busy:mode==='busy'};
 const bridge=createVoiceBridge({target:()=>target,offer:()=>{},offerBlocked:()=>blocked++,status:t=>status.push(t),sameTarget:()=>mode!=='switch',attach:()=>{},wait:async()=>{if(mode==='approval')await pause;},result:()=>{results++;return {sent:true};},api:async(p,o)=>{
 if(p.includes('cancel'))cancelCalls++;
 if(p==='/api/chat/start'){posts++;if(mode==='network')throw Error('connection lost');return {stream_id:'run'};}
 if(p.includes('/stream/status')){polls++;return {active:mode==='approval'&&polls===1};}
 return {session:{model:'m',model_provider:'p',messages:posts?[{role:'user',content:'request'},{role:'assistant',content:'final'}]:[]}};
 }});
 bridge.offer('first');const work=bridge.confirm();
 if(mode==='approval'){await new Promise(r=>setImmediate(r));bridge.offer('second');assert.equal(blocked,0);assert.equal(posts,1);assert.equal(results,0);bridge.reset();release();}
 await work;
 if(mode==='busy')assert.equal(posts,0);
 if(['busy','approval','switch','network'].includes(mode))assert.equal(results,0);
 assert.equal(cancelCalls,0);assert.ok(posts<=1);
 return {mode,posts,results,blocked};
}
(async()=>{for(const m of ['busy','approval','switch','network'])console.log(await scenario(m));console.log('PASS busy guard, waiting run + second request notice, Stop detaches without cancel, session switch, failed submission no retry');})().catch(e=>{console.error(e);process.exitCode=1;});
