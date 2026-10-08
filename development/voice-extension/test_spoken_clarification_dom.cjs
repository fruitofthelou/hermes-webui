'use strict';
// Execute the actual panel + browser adapter, not a replacement for bridge.route.
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
async function flush(){for(let i=0;i<30;i++)await Promise.resolve();}
function fixture(){
 const els={},timers=new Map();let next=0,now=0;
 class Element{constructor(tag){this.tag=tag;this.children=[];this.value='';}set id(v){this._id=v;els[v]=this;}get id(){return this._id;}append(...xs){this.children.push(...xs);}prepend(x){this.children.unshift(x);}insertBefore(x,b){this.children.splice(this.children.indexOf(b),0,x);}replaceChildren(...xs){this.children=xs;}setAttribute(k,v){this[k]=v;}}
 els.composerWrap=new Element('div');
 const state={pending:null,approval:null,calls:[],posts:[],feedback:[],active:true,readbackDelay:0,remainingReads:0};
 const ctx={console,Date,URL,performance:{now:()=>now},crypto:require('node:crypto').webcrypto,fetch:async()=>({ok:true}),document:{baseURI:'https://test.invalid/',createElement:t=>new Element(t),getElementById:id=>els[id]},window:{hermesExt:{register:()=>true}},S:{session:{session_id:'A'},activeProfile:'default',busy:false},attachLiveStream(){},setTimeout:(fn,ms)=>{const id=++next;timers.set(id,{fn,at:now+ms});return id;},clearTimeout:id=>timers.delete(id),api:async(p,o)=>{
  state.calls.push({p,o});
  if(p.startsWith('/api/clarify/pending')){if(state.remainingReads&&!--state.remainingReads)state.pending=null;return {pending:state.pending};}
  if(p.startsWith('/api/approval/pending'))return {pending:state.approval};
  if(p==='/api/clarify/respond'){state.posts.push(JSON.parse(o.body));if(state.readbackDelay)state.remainingReads=state.readbackDelay;else state.pending=null;return {ok:true};}
  if(p==='/api/chat/start'){state.posts.push({task:JSON.parse(o.body)});return {stream_id:'run'};}
  if(p.includes('stream/status'))return {active:state.active,stream_id:'run',task_outcome:{status:'succeeded'}};
  if(p.startsWith('/api/session'))return {session:{messages:[],model:'m',model_provider:'p'}};
  throw Error('unexpected endpoint '+p);
 }};
 vm.createContext(ctx);for(const name of ['panel.js','bridge.js'])vm.runInContext(fs.readFileSync(__dirname+'/'+name,'utf8'),ctx);
 const b=ctx.window.subscriptionVoiceBridge;
 async function tick(ms){const end=now+ms;for(let count=0;count<1000;count++){await flush();const due=[...timers].filter(([,t])=>t.at<=end).sort((a,b)=>a[1].at-b[1].at)[0];if(!due)break;now=due[1].at;timers.delete(due[0]);due[1].fn();}now=end;await flush();}
 const connect=()=>b.connect(async()=>({sent:true}),(text,isState)=>state.feedback.push(isState?JSON.parse(text):text));
 return {b,state,ctx,tick,connect,els};
}
const question=()=>({clarify_id:'exact-question-17',question:'Brooklyn or Boston?',choices_offered:['Brooklyn','Boston']});
(async()=>{
 // Pending question may arrive later, with no voice-owned task at all.
 const f=fixture();f.connect();await flush();assert.equal(f.state.posts.length,0);
 f.state.pending=question();await f.tick(2000);
 const published=f.state.feedback.find(x=>x?.pendingQuestion);assert.equal(published.pendingQuestion.clarify_id,'exact-question-17');assert.equal(published.pendingQuestion.session_id,'A');
 assert.equal(f.state.feedback.filter(x=>typeof x==='string'&&x.includes('Question:')).length,1);
 await f.b.transcript('Brook','item (not final)');assert.equal(f.state.posts.length,0);
 f.state.readbackDelay=3;
 const response=f.b.transcript(' Brooklyn ','final');await flush();await f.tick(300);assert.equal((await response).accepted,true);
 assert.deepEqual(f.state.posts,[{session_id:'A',clarify_id:'exact-question-17',response:'Brooklyn'}]);
 assert.ok(f.state.calls.filter(c=>c.p.startsWith('/api/clarify/pending')).length>=5);
 assert.equal(f.state.feedback.at(-2)?.pendingQuestion,null);
 await f.b.transcript('Brooklyn','final');
 f.b.offer('Brooklyn','late-native');await f.tick(2000);
 f.b.offer(JSON.stringify({v:1,action:'clarify',text:'Brooklyn'}),'late-structured');await f.tick(2000);
 assert.equal(f.state.posts.length,1,'late delegation cannot become a new task');f.b.reset();
 for(const mode of ['stale','wrong-session','wrong-profile','approval','reset']){
  const g=fixture();g.state.pending=question();g.connect();await flush();
  if(mode==='stale')g.state.pending={...question(),clarify_id:'replacement'};
  if(mode==='wrong-session')g.ctx.S.session.session_id='B';
  if(mode==='wrong-profile')g.ctx.S.activeProfile='other';
  if(mode==='approval')g.state.approval={approval_id:'permission'};
  if(mode==='reset')g.b.reset();
  assert.equal((await g.b.transcript('Brooklyn','final')).accepted,false,mode);assert.equal(g.state.posts.length,0,mode);g.b.reset();
 }
 // Target changes during the async preflight fail closed at point of use.
 const race=fixture();race.state.pending=question();race.connect();await flush();
 const originalApi=race.ctx.api;race.ctx.api=async(p,o)=>{const r=await originalApi(p,o);if(p.startsWith('/api/approval/pending'))race.ctx.S.session.session_id='B';return r;};
 assert.equal((await race.b.transcript('Brooklyn','final')).accepted,false);assert.equal(race.state.posts.length,0);race.b.reset();
 // Simultaneous finals cannot race into a second POST.
 const h=fixture();h.state.pending=question();h.connect();await flush();await Promise.all([h.b.transcript('Brooklyn','final'),h.b.transcript('Brooklyn','final')]);assert.equal(h.state.posts.length,1);h.b.reset();
 // Arbitrary speech never executes. Discovery is bounded and read-only.
 const i=fixture();i.connect();await flush();await i.b.transcript('Explain weather and climate','final');await i.tick(200000);const reads=i.state.calls.length;await i.tick(200000);assert.equal(i.state.calls.length,reads);assert.equal(i.state.posts.length,0);i.b.reset();
 // Structured independent queue stays a queue while the first task runs.
 const j=fixture();j.connect();await flush();j.b.offer(JSON.stringify({v:1,action:'queue',text:'Check weather'}),'task-1');await j.tick(2000);assert.equal(j.state.posts.length,1);
 await j.b.transcript('Also explain weather and climate in one sentence','final');assert.equal(j.state.posts.length,1);
 j.b.offer(JSON.stringify({v:1,action:'queue',text:'Explain weather and climate in one sentence'}),'task-2');await j.tick(2000);
 assert.equal(j.state.posts.length,1);assert.equal(j.state.calls.filter(c=>c.p==='/api/chat/steer').length,0);
 const queued=[...j.state.feedback].reverse().find(x=>x?.waiting?.length);assert.equal(queued.waiting[0].text,'Explain weather and climate in one sentence');
 const box=j.els['subscription-voice-handoff'].children[0];assert.ok(JSON.stringify(box.children.map(e=>e.children?.map(c=>c.textContent))).includes('Queued #2'));
 j.b.reset();await j.tick(1000);
 console.log('PASS actual panel transcript callback: exact-id POST + polled readback, pending discovery/publication, stale/target/profile/approval/reset guards, duplicate native handoff, bounded reads, structured independent queue');
})().catch(e=>{console.error(e);process.exitCode=1;});
