'use strict';
const assert=require('node:assert/strict');
const {classifyEvent}=require('./app.js');
assert.deepEqual(classifyEvent({type:'delegation.context.appended'}),{});
for(const type of ['delegation.execute','execution.requested','function_call.created','approval.requested','delegation.unknown'])assert.equal(classifyEvent({type}).stop,'delegation-or-execution-rejected');
console.log('PASS delegation context acknowledgement does not close call; execution and unknown delegation remain blocked');
