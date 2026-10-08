// Offline simulated browser/provider. No real login, microphone, or provider.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
async function run(mode) {
  let micStopped = false, pauses = 0, plays = 0, peerClosed = false, channelClosed = false;
  const sent = [], timers = new Map(); let timerID = 0, ch, peer;
  const els = Object.fromEntries(['start','stop','mute','voice','transcript','status','audio','delivery'].map(id=>[id,{textContent:'',disabled:false,value:'cove'}]));
  els.audio.pause=()=>pauses++; els.audio.play=()=>{plays++;return Promise.resolve();};
  const track={stop(){micStopped=true;},enabled:true};
  const media={getTracks:()=>[track],getAudioTracks:()=>[track]};
  class Peer {
    constructor(){peer=this;this.iceGatheringState='complete';this.connectionState='connected';this.localDescription={sdp:'simulated'};}
    addTrack(){} createOffer(){return Promise.resolve({});} setLocalDescription(){return Promise.resolve();}
    setRemoteDescription(){return Promise.resolve();} close(){peerClosed=true;}
    createDataChannel(){ch={readyState:'open',close(){channelClosed=true;},send(text){if(mode==='send-failure')throw Error('simulated');sent.push(JSON.parse(text));}};return ch;}
  }
  const ctx={S:{session:{session_id:'test'}},TextEncoder,URL,Date,document:{baseURI:"https://test.invalid/hermes/",getElementById:id=>els[id.replace("subscription-voice-","")],querySelector:()=>({content:'simulated'})},window:{isSecureContext:true,RTCPeerConnection:Peer,addEventListener(){}},navigator:{mediaDevices:{getUserMedia:async()=>media}},RTCPeerConnection:Peer,AbortController,MediaStream:function(){},setTimeout(fn,ms){const id=++timerID;timers.set(id,{fn,ms});return id;},clearTimeout(id){timers.delete(id);},fetch:async path=>({ok:true,json:async()=>path.endsWith('/capability')?{auth:'enabled'}:path.endsWith('/negotiations')?{id:'synthetic-job',capability:'synthetic-cap'}:{state:'ready',sdp:'simulated'}})};
  vm.runInNewContext(fs.readFileSync(__dirname+'/app.js','utf8'),ctx);
  await els.start.onclick();
  peer.ontrack({streams:[media]});assert.equal(plays,1);
  if(mode==='not-open')ch.readyState='closed';
  els.stop.onclick();
  assert.equal(micStopped,true);assert.ok(pauses>0);assert.equal(els.audio.srcObject,null);
  if(['send-failure','not-open'].includes(mode)){
    assert.match(els.status.textContent,/unconfirmed/);assert.equal(peerClosed,true);return;
  }
  assert.deepEqual(sent,[{type:'session.close'}]);
  assert.equal(peerClosed,false);assert.equal(channelClosed,false);assert.equal(els.start.disabled,true);
  els.stop.onclick();assert.equal(sent.length,1);
  peer.ontrack({streams:[media]});assert.equal(plays,1);
  ch.onmessage({data:JSON.stringify({type:'session.output_transcript.delta',delta:'must not appear'})});assert.equal(els.transcript.textContent,'');
  if(mode==='confirmed')ch.onmessage({data:JSON.stringify({type:'session.closed',reason:'close_requested'})});
  if(mode==='timeout'){
    const close=[...timers.values()].find(t=>t.ms===5000);assert.ok(close);close.fn();
  }
  if(mode==='channel-loss')ch.onclose();
  if(mode==='provider-error')ch.onmessage({data:JSON.stringify({type:'error'})});
  assert.match(els.status.textContent,mode==='confirmed'?/closure confirmed/:/unconfirmed|Data channel closed/);
  assert.equal(peerClosed,true);assert.equal(channelClosed,true);assert.equal(els.start.disabled,false);
  assert.equal(timers.size,0);
  await els.start.onclick();assert.match(els.status.textContent,/Waiting for peer/);
  ch.onmessage({data:JSON.stringify({type:'session.closed'})});
}
(async()=>{for(const mode of ['confirmed','timeout','channel-loss','provider-error','send-failure','not-open'])await run(mode);console.log('PASS: six simulated close scenarios; immediate mic/audio stop, one close request, silent acknowledgement, bounded timeout, cleanup and reconnect. No live provider test.');})().catch(e=>{console.error(e);process.exitCode=1;});
