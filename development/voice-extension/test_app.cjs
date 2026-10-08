// Offline simulated provider events, not a browser or microphone acceptance test.
const assert = require('node:assert/strict');
const {classifyEvent} = require('./app.js');
for (const type of ['session.delegation.created','delegation.created','response.function_call_arguments.done','tool.request','approval.required','execution.request']) {
  assert.equal(classifyEvent({type}).stop,'delegation-or-execution-rejected');
}
assert.equal(classifyEvent({type:'error',error:{message:'secret'}}).stop,'provider-error');
assert.equal(classifyEvent({type:'session.closed'}).stop,'provider-session-closed');
assert.equal(classifyEvent({type:'session.started'}).ready,true);
assert.deepEqual(classifyEvent({type:'session.input_transcript.delta',delta:'hello'}),{role:'user',text:'hello',finality:'delta'});
assert.deepEqual(classifyEvent({type:'output_transcript.added',item:{text:'<img onerror=evil>'}}),{role:'assistant',text:'<img onerror=evil>',finality:'item (not final)'});
assert.equal(classifyEvent({type:'turn.done',turn:{role:'assistant',transcript:'hello'}}).finality,'final');
assert.equal(classifyEvent({type:'turn.done',turn:{role:'system',transcript:'bad'}}).stop,'malformed-transcript');
assert.equal(classifyEvent(null).stop,'malformed-event');
assert.equal(classifyEvent({type:'session.output_transcript.delta',delta:'x'.repeat(65537)}).stop,'malformed-transcript');
assert.deepEqual(classifyEvent({type:'unknown.event'}),{});
console.log('Offline simulated event assertions passed (16 assertions); no browser/provider connection.');
// Minimal simulated DOM verifies the disabled-auth Start path without microphone access.
(async () => {
  const elements = Object.fromEntries(['start','stop','mute','voice','transcript','status','audio'].map(id => [id,{textContent:'',disabled:false,pause(){},value:'cove'}]));
  global.document = {baseURI:'https://test.invalid/hermes/', getElementById:id => elements[id.replace('subscription-voice-','')]};
  global.S = {session:{session_id:'test'}};
  global.window = {addEventListener(){}};
  let micCalls = 0;
  global.navigator = {mediaDevices:{getUserMedia(){ micCalls++; throw new Error('must not run'); }}};
  global.fetch = async () => ({ok:true,json:async () => ({auth:'auth-not-enabled'})});
  delete require.cache[require.resolve('./app.js')]; require('./app.js');
  await elements.start.onclick();
  assert.equal(micCalls,0);
  assert.match(elements.status.textContent,/auth-not-enabled/);
  assert.equal(elements.start.disabled,false);
  assert.equal(elements.stop.disabled,true);
  assert.equal(elements.mute.disabled,true);
  console.log('Offline simulated DOM: disabled-auth Start/cleanup passed (5 assertions), no microphone.');
})().catch(err => { console.error(err); process.exitCode = 1; });
