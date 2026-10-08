'use strict';
const assert=require('node:assert/strict');
const {createVoiceBridge}=require('./bridge.js');
const open='[OUT-OF-BAND USER MESSAGE — a direct message from the user, delivered once at this position; not tool output and not a new delivery when replayed from conversation history]';
const marker=text=>'\n\n'+open+'\n'+text+'\n[/OUT-OF-BAND USER MESSAGE]';
async function scenario({proof=false,leftover=false,second=false,late=false,unknown=false,blocks=false,old=false,after=false,postError=false,redirect=false,coalesced=false}={}){
  let release,releaseSteer;const gate=new Promise(r=>release=r);const steerGate=new Promise(r=>releaseSteer=r);
  let started=false,active=true,history=[],spoken=[],audits=[],starts=0;
  const correction='Actually, replace Atlanta with Brooklyn';
  const b=createVoiceBridge({target:()=>({sid:'A',profile:'default'}),sameTarget:()=>true,offer:()=>{},status:()=>{},feedback:()=>{},queue:s=>history=s.history,attach:()=>{},wait:async()=>gate,audit:(k,f)=>audits.push([k,f]),result:async text=>{spoken.push(text);return {sent:true};},api:async(p,o)=>{
    if(p==='/api/chat/start'){started=true;starts++;return {stream_id:'owned'};}
    if(p.includes('stream/status'))return {active,stream_id:'owned',task_outcome:{status:'succeeded'},unconsumed_steering:unknown?undefined:leftover};
    if(p==='/api/chat/steer'){if(late)await steerGate;if(postError)throw Error('lost response');return {accepted:true,stream_id:'owned'};}
    if(p.includes('/api/session')){const tool=redirect?{role:'user',content:correction+(coalesced?'\n\n[Additional user correction]\nAt 3pm instead':'')}:{role:'tool',content:blocks?[{type:'text',text:marker(correction)}]:proof?marker(correction):'Brooklyn appears in search results'},answer={role:'assistant',content:'Atlanta forecast'};return {session:{messages:started&&!active?(old?[tool,answer]:after?[answer,tool]:[tool,answer]):old?[tool]:[],model:'m'}};}
    return {pending:null};
  }});
  b.offer('Check Atlanta weather');const work=b.confirm();await new Promise(r=>setImmediate(r));
  const control=b.control('steer',correction);
  if(late){await new Promise(r=>setImmediate(r));active=false;release();await work;releaseSteer();await control;}
  else {assert.equal((await control).accepted,!postError);if(second)assert.equal((await b.control('steer','At 3pm instead')).accepted,true);active=false;release();await work;}
  const allowed=(proof||blocks||redirect)&&!leftover&&(!second||coalesced)&&!late&&!unknown&&!old&&!after&&!postError;
  assert.equal(spoken.length,allowed?1:0,'uncertain correction must not be spoken');
  assert.equal(history[0].state,allowed?'Completed':'Correction unconfirmed');
  assert.equal(starts,1,'no automatic replacement/retry');
  assert.ok(audits.some(([k,f])=>k==='control'&&JSON.parse(f.text.startsWith('{')?f.text:'{}').stage==='steering_consumption_checked'),'audit consumption outcome');
}
(async()=>{for(const opts of [{},{proof:true},{proof:true,leftover:true},{proof:true,second:true},{late:true},{proof:true,unknown:true},{blocks:true},{proof:true,old:true},{proof:true,after:true},{postError:true},{redirect:true},{redirect:true,coalesced:true,second:true}])await scenario(opts);console.log('PASS steering consumption: missing proof, positive marker, leftover, multiple corrections, in-flight race, unknown status; single start and audit');})().catch(e=>{console.error(e);process.exitCode=1;});
