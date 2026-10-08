'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
async function run(mode){
 let channel,sender,id=0;const timers=new Map(),traces=[];
 const els=Object.fromEntries(['start','stop','mute','voice','status','delivery','audio','transcript'].map(k=>[k,{textContent:'',value:'cove',pause(){},play:async()=>{}}]));
 class Peer{constructor(){this.iceGatheringState='complete';this.localDescription={sdp:'fixture'};}addTrack(){}async createOffer(){return {};}async setLocalDescription(){}async setRemoteDescription(){}close(){}createDataChannel(){channel={readyState:'open',send(){},close(){}};return channel;}}
 const ctx={S:{session:{session_id:'fixture'}},URL,Date,TextEncoder,AbortController,RTCPeerConnection:Peer,document:{baseURI:'https://fixture.invalid/',getElementById:key=>els[key.replace('subscription-voice-','')]},window:{isSecureContext:true,RTCPeerConnection:Peer,addEventListener(){},subscriptionVoiceBridge:{connect:f=>sender=f,reset(){},transcript(){}}},navigator:{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[],getAudioTracks:()=>[]})}},fetch:async(url,o)=>{if(url.endsWith('/diagnostics'))traces.push(JSON.parse(o.body));return {ok:true,json:async()=>url.endsWith('/capability')?{auth:'enabled'}:url.endsWith('/negotiations')?{id:'fixture',capability:'fixture'}:{state:'ready',sdp:'fixture'}};},setTimeout:(f,ms)=>{timers.set(++id,{f,ms});return id;},clearTimeout:id=>timers.delete(id)};
 vm.runInNewContext(fs.readFileSync(__dirname+'/app.js','utf8'),ctx);await els.start.onclick();channel.onopen();
 const receipt=sender('Backend answer.',null,'exact');const event=e=>channel.onmessage({data:JSON.stringify(e)});
 if(mode==='end_call')els.stop.onclick();
 else if(mode==='connection_closed')channel.onclose();
 else if(mode==='output_timeout')[...timers.values()].find(t=>t.ms===15000).f();
 else if(mode==='turn_completion_timeout'){event({type:'output_transcript.added',item:{text:'partial'}});[...timers.values()].find(t=>t.ms===30000).f();}
 else if(mode==='quota')event({type:'error',error:{code:'insufficient_quota'}});
 else event({type:'turn.done',turn:{role:'assistant',transcript:mode==='complete'?'Answer exact. Backend answer.':'Backend answer.'}});
 const result=await receipt;
 if(mode==='complete'){assert.equal(result.sent,true);assert.equal(result.receiptConfirmed,true);}
 else if(mode==='quota'){assert.equal(result.providerFailed,true);assert.equal(result.reason,'quota');}
 else {assert.equal(result.sent,false);assert.equal(result.reason,mode==='markerless'?'missing_receipt':mode);assert.equal(result.providerFailed,false);assert.equal(result.receiptConfirmed,false);assert.equal(result.providerTurnComplete,mode==='markerless');assert.ok(traces.some(t=>t.event==='delivery_unconfirmed'&&t.code===result.reason));}
 assert.equal(result.audibleConfirmed,undefined);
 if(['complete','markerless'].includes(mode))assert.ok(traces.some(t=>t.event==='provider_turn_complete'));
 assert.ok(traces.every(t=>!JSON.stringify(t).includes('Backend answer')));
}
(async()=>{for(const mode of ['markerless','complete','end_call','connection_closed','output_timeout','turn_completion_timeout','quota'])await run(mode);console.log('PASS app receipt-less final without deltas, receipt, turn metadata, timeout/end/disconnect uncertainty and actual provider failure');})().catch(e=>{console.error(e);process.exitCode=1;});
