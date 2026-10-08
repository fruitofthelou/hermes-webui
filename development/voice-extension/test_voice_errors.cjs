'use strict';
const assert=require('node:assert/strict');
const {voiceFailureCategory,safeProviderError}=require('./app.js');
for(const [error,category] of [
 [{code:'insufficient_quota'},'quota'],[{message:'Payment required, insufficient credits'},'quota'],
 [{code:'rate_limit_exceeded'},'rate_limit'],[{message:'Model blocked by guardrail'},'policy'],
 [{code:'invalid_api_key'},'authentication'],[{message:'request timed out'},'timeout'],
 [{code:'invalid_value',param:'content'},'invalid_request'],[{code:'internal_error'},'provider']])assert.equal(voiceFailureCategory(error),category);
assert.ok(!JSON.stringify(safeProviderError({message:'Bearer sensitive-value api_key=private-value'})).includes('sensitive-value'));
console.log('PASS voice errors: quota, rate limit, policy, authentication, timeout, invalid request, unknown; credential-safe diagnostics');
