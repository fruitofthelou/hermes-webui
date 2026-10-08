'use strict';
const assert=require('node:assert/strict');const {createRequestCapture}=require('./bridge.js');
const c=createRequestCapture();
for(const text of ['Hello','Can you look up weather?','Actually Atlanta','and also'])assert.equal(c.consume(text,'final'),null);
c.arm();assert.equal(c.consume('Manual fallback request','final'),'Manual fallback request');
c.reset();assert.equal(c.consume('Can you look up weather?','final'),null);
console.log('PASS no keyword-based intent, correction or completeness inference; explicit manual fallback only');
