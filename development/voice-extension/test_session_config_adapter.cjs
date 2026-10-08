'use strict';
// Actual app startup/data-channel callbacks under an offline VM fixture.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
(async()=>{
 const config={instructions:'offline-contract',delegation:{type:'client'},audio:{output:{voice:'arbor'}}};
 const sent=[],audits=[],elements={};let peer,bridgeConnects=0;
 for(const id of ['start','stop','mute','voice','transcript','status','audio'])elements[id]={value:'arbor',textContent:'',pause(){}};
 class Peer{
  constructor(){peer=this;this.iceGatheringState='complete';}
  addTrack(){} createDataChannel(){return this.channel={readyState:'open',send:x=>sent.push(JSON.parse(x))};}
  async createOffer(){return {sdp:'offline-offer'};} async setLocalDescription(x){this.localDescription=x;}
  async setRemoteDescription(){this.channel.onopen();}
  close(){} removeEventListener(){}
 }
 const ctx={URL,TextEncoder,AbortController,console,Date,RTCPeerConnection:Peer,
  setTimeout:()=>1,clearTimeout(){},S:{session:{session_id:'isolated'}},
  document:{baseURI:'https://offline.invalid/',getElementById:id=>elements[id.replace('subscription-voice-','')]},
  navigator:{mediaDevices:{getUserMedia:async()=>({getAudioTracks:()=>[],getTracks:()=>[]})}},
  window:{isSecureContext:true,RTCPeerConnection:Peer,addEventListener(){},subscriptionVoiceBridge:{connect(){bridgeConnects++;},reset(){}}},
  fetch:async(url,o={})=>{
   const path=new URL(url).pathname;
   if(path.endsWith('/audit')){audits.push(JSON.parse(o.body));return {ok:true};}
   let data={};
   if(path.endsWith('/capability'))data={auth:'enabled'};
   if(path.endsWith('/negotiations'))data={id:'synthetic-job',capability:'synthetic-cap'};
   if(path.endsWith('/poll'))data={state:'ready',sdp:'offline-answer',session_config:config};
   return {ok:true,json:async()=>data};
  }};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(__dirname+'/app.js','utf8'),ctx);
 await elements.start.onclick();
 assert.deepEqual(sent,[{type:'session.update',session:config}]);assert.equal(bridgeConnects,1);
 const evidence=stage=>audits.filter(a=>a.kind==='control').map(a=>JSON.parse(a.text)).find(a=>a.stage===stage);
 assert.equal(evidence('session_config_sent').instructions_match,true);
 peer.channel.onmessage({data:JSON.stringify({type:'session.updated',session:config})});
 assert.equal(evidence('session_config_echo').instructions_match,true);
 assert.ok(!JSON.stringify(audits).includes('offline-contract'));
 console.log('PASS offline actual adapter: helper config sent unchanged, send evidence and provider echo compared, no instructions persisted');
})().catch(e=>{console.error(e);process.exitCode=1;});
