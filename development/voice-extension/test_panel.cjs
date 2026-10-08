'use strict';
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const els={};class Element{constructor(tag){this.tag=tag;this.children=[];}set id(v){this._id=v;els[v]=this;}get id(){return this._id;}append(...v){this.children.push(...v);for(const x of v)x.parentNode=this;}prepend(x){this.children.unshift(x);x.parentNode=this;}setAttribute(k,v){this[k]=v;}}
const composer=new Element('div');els.composerWrap=composer;
vm.runInNewContext(fs.readFileSync(__dirname+'/panel.js','utf8'),{document:{createElement:t=>new Element(t),getElementById:id=>els[id]},window:{hermesExt:{register:()=>true}}});
assert.equal(els['subscription-voice-panel'].parentNode,composer);
assert.equal(els['subscription-voice-panel'].children[0].textContent,'Live voice');
assert.equal(els['subscription-voice-audio'].parentNode.className,'voice-diagnostics');
assert.equal(els['subscription-voice-transcript'].parentNode.className,'voice-diagnostics');
assert.equal(els['subscription-voice-status'].role,'status');
console.log('PASS composer mount, accessible status, hidden diagnostic player/transcript; simulated DOM not visual browser acceptance');
