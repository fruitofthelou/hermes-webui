'use strict';
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const els={};class E{constructor(tag){this.tag=tag;this.children=[];this.value='';}set id(v){this._id=v;els[v]=this;}get id(){return this._id;}append(...xs){this.children.push(...xs);}prepend(x){this.children.unshift(x);}insertBefore(x,b){this.children.splice(this.children.indexOf(b),0,x);}replaceChildren(...xs){this.children=xs;}setAttribute(k,v){this[k]=v;}}
els.composerWrap=new E('div');let posts=0,release;const gate=new Promise(r=>release=r);
const ctx={console,Date,URL,clearTimeout(){},fetch:async()=>({ok:true}),document:{baseURI:'https://test.invalid/',createElement:t=>new E(t),getElementById:id=>els[id]},window:{hermesExt:{register:()=>true}},S:{session:{session_id:'A'},activeProfile:'default',busy:false},attachLiveStream(){},setTimeout:f=>{gate.then(f);},api:async(p,o)=>{if(p==='/api/chat/start'){posts++;return {stream_id:'run'};}if(p.includes('stream/status'))return {active:true};return {session:{messages:[],model:'m',model_provider:'p'}};}};
vm.createContext(ctx);for(const name of ['panel.js','bridge.js'])vm.runInContext(fs.readFileSync(__dirname+'/'+name,'utf8'),ctx);
const box=els['subscription-voice-handoff'].children[0];const confirm=box.children.find(e=>e.textContent==='Confirm request');
assert.equal(confirm.disabled,true);
ctx.window.subscriptionVoiceBridge.transcript('Can you look up weather and also','final');assert.equal(confirm.disabled,true);assert.equal(posts,0);ctx.window.subscriptionVoiceBridge.reset();
// Manual diagnostic fallback uses the textarea; native handoffs auto-dispatch after settling.
const draft=els['subscription-voice-request'];draft.value='Say hello';draft.oninput();
assert.equal(draft.value,'Say hello');assert.equal(confirm.disabled,false);
draft.value='Say hello in Atlanta';draft.oninput();assert.equal(confirm.disabled,false);
confirm.onclick();setImmediate(()=>{try{assert.equal(posts,1);draft.value='Say goodbye';draft.oninput();assert.equal(confirm.disabled,false);confirm.onclick();assert.equal(posts,1);ctx.window.subscriptionVoiceBridge.reset();release();console.log('PASS actual panel/bridge handlers: capture enables Confirm, click submits once, second Confirm queues while running');}catch(e){console.error(e);process.exitCode=1;}});
