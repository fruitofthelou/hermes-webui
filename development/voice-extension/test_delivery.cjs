'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {createTranscriptAssembler}=require('./bridge.js');
const a=createTranscriptAssembler();
assert.equal(a.consume(' Please','item (not final)'),'Please');
assert.equal(a.consume(' ask','item (not final)'),'Please ask');
assert.equal(a.consume(' Hermes','item (not final)'),'Please ask Hermes');
assert.equal(a.consume('Please ask Hermes','final'),'Please ask Hermes');
assert.equal(a.consume(' to tell','item (not final)'),'Please ask Hermes to tell');
a.reset();assert.equal(a.consume('x','delta'),null);
async function run(mode){
 let ch,sender,feedback;const sent=[],timers=new Map();let tid=0;
 const els=Object.fromEntries(['start','stop','mute','voice','transcript','status','audio','delivery'].map(k=>[k,{textContent:'',value:'cove'}]));
 els.audio.pause=()=>{};els.audio.play=async()=>{};
 class Peer{constructor(){this.iceGatheringState='complete';this.localDescription={sdp:'simulated'};}addTrack(){}async createOffer(){return {};}async setLocalDescription(){}async setRemoteDescription(){}close(){}createDataChannel(){ch={readyState:'open',close(){},send(t){if(mode==='throw')throw Error('synthetic failure');sent.push(JSON.parse(t));}};return ch;}}
 const ctx={S:{session:{session_id:'test'}},URL,Date,TextEncoder,AbortController,RTCPeerConnection:Peer,MediaStream:function(){},document:{baseURI:'https://test.invalid/',getElementById:id=>els[id.replace('subscription-voice-','')]},window:{isSecureContext:true,RTCPeerConnection:Peer,addEventListener(){},subscriptionVoiceBridge:{connect:(f,g)=>{sender=f;feedback=g;},reset(){},transcript(){}}},navigator:{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[{stop(){}}],getAudioTracks:()=>[]})}},fetch:async p=>({ok:true,json:async()=>p.endsWith('/capability')?{auth:'enabled'}:p.endsWith('/negotiations')?{id:'j',capability:'c'}:{state:'ready',sdp:'simulated'}}),setTimeout(f,ms){timers.set(++tid,{f,ms});return tid;},clearTimeout:id=>timers.delete(id)};
 vm.runInNewContext(fs.readFileSync(__dirname+'/app.js','utf8'),ctx);await els.start.onclick();ch.onopen();
 if(mode==='state'||mode==='clarification'){
  const source='Long state weather climate 😀 '.repeat(100);feedback(source,mode==='state');
  assert.ok(sent.length>1);assert.ok(sent.every(x=>Buffer.byteLength(x.content[0].text)<=500));
  assert.ok(sent.every(x=>x.channel===(mode==='state'?'commentary':'speakable')));
  assert.ok(sent.map(x=>x.content[0].text).join('').includes(source));
  els.stop.onclick();ch.onmessage({data:JSON.stringify({type:'session.closed'})});return;
 }
 ch.onmessage({data:JSON.stringify({type:'input_transcript.added',item:{text:'request'}})});assert.equal(els.audio.muted,true);
 ch.onmessage({data:JSON.stringify({type:'turn.done',turn:{role:'user',transcript:'request'}})});
 ch.onmessage({data:JSON.stringify({type:'output_transcript.added',item:{text:'working'}})});assert.equal(els.audio.muted,false);
 if(mode==='barge'){
  const receipt=sender('Long answer.',null,'barge');
  const event=e=>ch.onmessage({data:JSON.stringify(e)});
  event({type:'turn.delta',turn_id:'old'});event({type:'output_transcript.added',item:{text:'Old answer'}});
  event({type:'input_transcript.added',item:{text:'Stop talking'}});assert.equal(els.audio.muted,true);
  event({type:'output_transcript.added',item:{text:'stale fragment'}});assert.equal(els.audio.muted,true);
  event({type:'turn.done',turn:{role:'user',transcript:'Stop talking. One sentence instead.'}});
  event({type:'turn.delta',turn_id:'old'});event({type:'output_transcript.added',item:{text:'still stale'}});assert.equal(els.audio.muted,true);
  event({type:'turn.delta',turn_id:'new'});event({type:'output_transcript.added',item:{text:'New short response'}});assert.equal(els.audio.muted,false);
  assert.equal((await receipt).interrupted,true);els.stop.onclick();event({type:'session.closed'});return;
 }
 if(mode==='complete'){
  const receipt=sender('Hello from Hermes.',null,'probe');
  ch.onmessage({data:JSON.stringify({type:'turn.done',turn:{role:'assistant',transcript:'Answer probe. Hello from Hermes.'}})});
  assert.equal((await receipt).sent,true);assert.equal(els.audio.muted,false);
  els.stop.onclick();ch.onmessage({data:JSON.stringify({type:'session.closed'})});return;
 }
 if(['quota','rate_limit','provider_timeout','disconnect'].includes(mode)){
  const receipt=sender('Hello from Hermes.',null,'probe');
  if(mode==='disconnect')ch.onclose();
  else ch.onmessage({data:JSON.stringify({type:'error',error:{code:mode==='quota'?'insufficient_quota':mode==='rate_limit'?'rate_limit_exceeded':'request_timeout'}})});
  const outcome=await receipt;assert.equal(outcome.sent,false);assert.equal(timers.size,0);
  assert.equal(els.start.disabled,false);assert.equal(els.stop.disabled,true);
  if(mode!=='disconnect')assert.match(els.status.textContent,/no automatic retry/);
  assert.equal(sent.filter(x=>x.type==='session.context.append').length,1);return;
 }
 if(mode==='markerless'){
  const receipt=sender('Hello from Hermes.',null,'probe');
  ch.onmessage({data:JSON.stringify({type:'output_transcript.added',item:{text:'Hello from Hermes.'}})});
  ch.onmessage({data:JSON.stringify({type:'turn.done',turn:{role:'assistant',transcript:'Hello from Hermes.'}})});
  const outcome=await receipt;assert.equal(outcome.sent,false);assert.equal(outcome.reason,'missing_receipt');assert.ok(![...timers.values()].some(t=>[15000,30000].includes(t.ms)));
  ch.onmessage({data:JSON.stringify({type:'input_transcript.added',item:{text:'Thank you'}})});
  assert.ok(!els.delivery.textContent.includes('You interrupted'));els.stop.onclick();ch.onmessage({data:JSON.stringify({type:'session.closed'})});return;
 }
 if(mode==='closed')ch.readyState='closed';
 for(const [id,t] of timers){if(t.ms===10000)timers.delete(id);}
 let receipt=sender('Hello from Hermes.'+(mode==='long'?'😀'.repeat(400):''),mode==='delegation'?'d-test':null);
 const asyncReceipt=receipt?.then; if(asyncReceipt)receipt={sent:true};
 assert.equal(receipt.sent,!['closed','throw'].includes(mode));
 if(receipt.sent){assert.equal(sent[0].type,mode==='delegation'?'delegation.context.append':'session.context.append');assert.equal(sent[0].channel,'speakable');assert.match(sent[0].content[0].text,/Hello from Hermes/);for(const msg of sent){assert.equal(msg.content[0].type,'input_text');assert.ok(Buffer.byteLength(msg.content[0].text,'utf8')<=500);}if(mode==='delegation')assert.equal(sent[0].delegation_item_id,'d-test');assert.match(els.delivery.textContent,/waiting/);
 if(mode==='error'){ch.onmessage({data:JSON.stringify({type:'error',error:{code:'invalid_event',type:'invalid_request_error'}})});assert.match(els.delivery.textContent,/Provider error/);assert.equal(timers.size,0);}else if(mode==='output'){ch.onmessage({data:JSON.stringify({type:'output_transcript.added',item:{text:'Hello from Hermes.'}})});assert.match(els.delivery.textContent,/Provider output observed/);assert.equal(els.status.textContent,els.delivery.textContent);ch.onmessage({data:JSON.stringify({type:'turn.done',turn:{role:'assistant',transcript:'Hello from Hermes.'}})});}else{[...timers.values()].find(t=>t.ms===15000).f();assert.match(els.delivery.textContent,/no provider output/);}}
 els.stop.onclick();ch.onmessage({data:JSON.stringify({type:'session.closed'})});assert.equal(timers.size,0);
}
(async()=>{for(const m of ['closed','throw','timeout','output','error','long','delegation','state','clarification','complete','markerless','quota','rate_limit','provider_timeout','disconnect','barge'])await run(m);console.log('PASS transcript assembly, send receipt, closed/send-failure detection, output observation, timeout and cleanup — simulated provider only');})().catch(e=>{console.error(e);process.exitCode=1;});
