'use strict';
const assert=require('node:assert/strict');const {contextChunks,safeProviderError}=require('./app.js');
for(const text of ['x'.repeat(6000),'😀'.repeat(800),'Weather\nClimate — café '.repeat(250)]){
 const chunks=contextChunks(text);assert.equal(chunks.join(''),text);assert.ok(chunks.every(x=>Buffer.byteLength(x)<=500));assert.ok(chunks.length>1);
}
const e=safeProviderError({code:'invalid_value',param:'content',type:'invalid_request_error',message:'content is too long; Bearer private-token api_key=private-key'});
assert.equal(e.param,'content');assert.ok(e.message.includes('content is too long'));assert.ok(!e.message.includes('private-token'));assert.ok(!e.message.includes('private-key'));
console.log('PASS UTF-8 exact reconstruction and bounds; provider error useful message retained with credential redaction');
