'use strict';
// Offline adapter instrumentation contract; never asserts model compliance.
const assert=require('node:assert/strict');
const {sessionConfigEvidence}=require('./app.js');
const sent={instructions:'private-contract',delegation:{type:'client'},audio:{output:{voice:'arbor'}},token:'do-not-log'};
assert.deepEqual(sessionConfigEvidence(sent,sent),{
  instructions_present:true,instructions_chars:16,instructions_match:true,
  delegation_client:true,voice_match:true
});
assert.equal(sessionConfigEvidence({...sent,instructions:'different'},sent).instructions_match,false);
assert.equal(sessionConfigEvidence({delegation:{type:'client'}},sent).instructions_match,null);
assert.equal(sessionConfigEvidence(undefined,sent).instructions_present,false);
assert.equal(sessionConfigEvidence(sent,null).instructions_match,null);
assert.equal(sessionConfigEvidence({},sent).voice_match,null);
const evidence=JSON.stringify(sessionConfigEvidence(sent,sent));
assert.ok(!evidence.includes('private-contract')&&!evidence.includes('do-not-log')&&!evidence.includes('arbor'));
console.log('PASS offline session config evidence: exact match/mismatch, missing echo unknown, no config contents');
