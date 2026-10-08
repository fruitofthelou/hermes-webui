'use strict';
// GPT-Live vocabulary pinned to Hermes Talk 2e5ef4f; not Realtime response.* events.
function classifyEvent(e) {
  if (!e || typeof e !== 'object' || typeof e.type !== 'string') return {stop:'malformed-event'};
  const t = e.type;
  // Exact acknowledgement of our context append; never an execution request.
  if (t === 'delegation.context.appended') return {};
  if (/delegation|function_call|tool|approval|execution|command/.test(t)) return {stop:'delegation-or-execution-rejected'};
  if (t === 'error') return {stop:'provider-error'}; // Never render provider error text.
  if (t === 'session.closed') return {stop:'provider-session-closed'};
  if (t === 'session.started') return {ready:true};
  let role, text, finality;
  if (t === 'session.input_transcript.delta' || t === 'session.output_transcript.delta') {
    role = t.includes('input') ? 'user' : 'assistant'; text = e.delta; finality = 'delta';
  } else if (t === 'input_transcript.added' || t === 'output_transcript.added') {
    role = t.startsWith('input') ? 'user' : 'assistant'; text = e.item?.text; finality = 'item (not final)';
  } else if (t === 'turn.done') {
    role = e.turn?.role; text = e.turn?.transcript; finality = 'final';
  } else return {};
  if (!['user','assistant'].includes(role) || typeof text !== 'string' || text.length > 65536) return {stop:'malformed-transcript'};
  return {role,text,finality};
}
function matchesDeliveryReceipt(event,marker){return event?.type==='turn.done' && event.turn?.role==='assistant' && typeof marker==='string' && typeof event.turn?.transcript==='string' && event.turn.transcript.includes(marker);}
function voiceFailureCategory(error){
  const e=safeProviderError(error),s=(e.code+' '+e.type+' '+e.message).toLowerCase();
  if(/quota|insufficient.credit|billing|payment|usage.limit/.test(s))return 'quota';
  if(/rate.limit|too.many.requests|429/.test(s))return 'rate_limit';
  if(/guardrail|data.policy|policy.block/.test(s))return 'policy';
  if(/unauthoriz|authentication|invalid.api.key|401|403/.test(s))return 'authentication';
  if(/timeout|timed.out/.test(s))return 'timeout';
  if(/invalid.value|invalid.request|content/.test(s))return 'invalid_request';
  return 'provider';
}
function contextChunks(text,maxBytes=500){
  if(typeof text!=='string')throw Error('invalid-context-text');
  const chunks=[];let chunk='';const enc=new TextEncoder();
  for(const char of text){if(enc.encode(chunk+char).length>maxBytes){chunks.push(chunk);chunk='';}chunk+=char;}
  if(chunk)chunks.push(chunk);return chunks;
}
function safeProviderError(error){
  // Keep useful provider diagnostics, never raw frames/headers/audio/SDP.
  const clean=v=>String(v||'').replace(/Bearer\s+\S+|sk-[\w-]{12,}|eyJ[\w-]+\.[\w-]+\.[\w-]+/gi,'[REDACTED]').replace(/((?:password|secret|api[_ -]?key|access_token|refresh_token)\s*[=:]\s*)[^\s,;]+/gi,'$1[REDACTED]').slice(0,2000);
  return {code:clean(error?.code),type:clean(error?.type),param:clean(error?.param),message:clean(error?.message)};
}
// Metadata only: a provider session event may omit settings. Missing is unknown,
// never evidence of acceptance or model compliance. Do not persist prompt text.
function sessionConfigEvidence(config,expected){
  const instructions=config?.instructions,voice=config?.audio?.output?.voice;
  return {
    instructions_present:typeof instructions==='string',
    instructions_chars:typeof instructions==='string'?instructions.length:0,
    instructions_match:typeof instructions==='string'&&typeof expected?.instructions==='string'?instructions===expected.instructions:null,
    delegation_client:config?.delegation?.type==='client',
    voice_match:typeof voice==='string'&&typeof expected?.audio?.output?.voice==='string'?voice===expected.audio.output.voice:null
  };
}
if (typeof module !== 'undefined') module.exports = {classifyEvent,matchesDeliveryReceipt,contextChunks,safeProviderError,voiceFailureCategory,sessionConfigEvidence};
if (typeof document !== 'undefined') {
  const $ = id => document.getElementById('subscription-voice-' + id);
  if (!$('start')) throw new Error('voice-panel-not-mounted');
  const proxy = path => new URL('api/extensions/subscription-voice/sidecar/' + path.replace(/^\//,''), document.baseURI).href;
  let traceSequence=0;let traceSession='call-'+Date.now().toString(36);
  window.subscriptionVoiceTraceSession=()=>traceSession;
  const trace=window.subscriptionVoiceTrace=(event,fields={})=>fetch(proxy('/diagnostics'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({event,...fields,client_sequence:++traceSequence,trace_session:traceSession})}).then(r=>{if(!r.ok)status('Diagnostic write failed — coverage incomplete');}).catch(()=>status('Diagnostics unavailable — coverage incomplete'));
  const audit=window.subscriptionVoiceAudit=(kind,fields={})=>fetch(proxy('/audit'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,...fields,client_sequence:++traceSequence,trace_session:traceSession})}).then(r=>{if(!r.ok)status('Audit write failed — diagnostic coverage incomplete');}).catch(()=>status('Audit unavailable — diagnostic coverage incomplete'));
  const browserFailure=(kind,error)=>{trace('browser_error',{stage:kind,error_type:error?.name||'Error'});audit('browser_error',{text:JSON.stringify({stage:kind,error_type:error?.name||'Error',message:String(error?.message||error||'Unknown error').slice(0,2000)})});};
  window.addEventListener('error',event=>browserFailure('uncaught',event.error));
  window.addEventListener('unhandledrejection',event=>browserFailure('unhandled_rejection',event.reason));
  let incompleteTimer=null,deliveryMarker=null;
  // Local barge-in is authoritative: stale output must not undo the mute.
  let speechActive=false,suppressedTurn=false,currentTurnId=null,suppressedTurnId=null;
  let startupStage='idle',deliveryResolve=null,activeRequestId=null,observedOutput=false;
  const settleDelivery=value=>{const resolve=deliveryResolve;deliveryResolve=null;clearTimeout(deliveryTimer);deliveryTimer=null;awaitingResponse=false;resolve?.(value);};
  const unconfirmedDelivery=(reason,providerTurnComplete=false)=>{trace('delivery_unconfirmed',{request_id:activeRequestId,code:reason});return {sent:false,reason,providerTurnComplete,receiptConfirmed:false,providerFailed:false};};
  let generation = 0, pc = null, stream = null, channel = null, abort = null, muted = false;
  let closing = false, closeTimer = null, deliveryTimer=null, awaitingResponse=false;
  const sendContext=(text,id=null,stateOnly=false)=>{
    if(channel?.readyState!=='open'||closing)throw Error('voice-channel-unavailable');
    const chunks=contextChunks(text),type=id?'delegation.context.append':'session.context.append';
    chunks.forEach((chunk,index)=>{
      audit('voice_send',{direction:'out',request_id:activeRequestId,event_type:type,text:JSON.stringify({channel:stateOnly?'commentary':'speakable',chunk_index:index,chunk_count:chunks.length,bytes:new TextEncoder().encode(chunk).length,text:chunk})});
      channel.send(JSON.stringify({type,...(id?{delegation_item_id:id}:{}),channel:stateOnly?'commentary':'speakable',content:[{type:'input_text',text:chunk}]}));
    });
  };
  function deliveryStatus(text){
    let el=$('delivery');
    if(!el){el=document.createElement('p');el.id='subscription-voice-delivery';$('status').parentNode.append(el);}
    el.textContent=text;
    $('status').textContent=text;
  }
  const status = text => { $('status').textContent = text; };
  function silence() {
    clearTimeout(incompleteTimer);if(deliveryResolve)settleDelivery(unconfirmedDelivery('end_call'));window.subscriptionVoiceBridge?.reset('end_call');
    stream?.getTracks().forEach(t => t.stop()); stream = null;
    $('audio').pause(); $('audio').srcObject = null;
    $('mute').disabled = true;
  }
  function cleanup() {
    clearTimeout(incompleteTimer);
    if(deliveryResolve){settleDelivery(unconfirmedDelivery('connection_closed'));deliveryStatus('Voice connection stopped before result delivery — delivery unconfirmed; inspect chat');}
    trace('call_stopped',{stage:'cleanup'});
    window.subscriptionVoiceBridge?.reset('connection_cleanup');
    clearTimeout(deliveryTimer);deliveryTimer=null;awaitingResponse=false;
    clearTimeout(closeTimer); closeTimer = null; closing = false;
    speechActive=false;suppressedTurn=false;currentTurnId=null;suppressedTurnId=null;
    abort?.abort(); abort = null;
    if (channel) { channel.onclose = null; channel.onerror = null; channel.close(); channel = null; }
    if (pc) { pc.onconnectionstatechange = null; pc.close(); pc = null; }
    stream?.getTracks().forEach(t => t.stop()); stream = null;
    $('audio').pause(); $('audio').srcObject = null;
    muted = false; $('mute').textContent = 'Mute mic'; $('mute').disabled = true;
    $('start').disabled = false; $('stop').disabled = true;
  }
  function stop(reason = 'Stopped') { trace('call_stopped',{stage:startupStage,code:reason.replace(/[^A-Za-z0-9_.:-]/g,'_').slice(0,80)});generation++; cleanup(); status(reason); }
  $('stop').onclick = () => {
    if (closing) return;
    silence();
    if (!channel || channel.readyState !== 'open') {
      stop('Stopped locally — provider closure unconfirmed'); return;
    }
    closing = true;
    $('stop').disabled = true; $('start').disabled = true;
    status('Stopped audio — waiting for provider closure');
    closeTimer = setTimeout(() => stop('Stopped locally — provider closure unconfirmed (timeout)'), 5000);
    try { channel.send(JSON.stringify({type:'session.close'})); }
    catch (_) { stop('Stopped locally — provider closure unconfirmed (send failed)'); }
  };
  $('mute').onclick = () => {
    if (!stream) return;
    muted = !muted; stream.getAudioTracks().forEach(t => { t.enabled = !muted; });
    $('mute').textContent = muted ? 'Unmute mic' : 'Mute mic';
  };
  $('start').onclick = async () => {
    const gen = ++generation;traceSequence=0;traceSession='call-'+Date.now().toString(36)+'-'+gen;trace('call_started');
    $('start').disabled = true; $('stop').disabled = false; $('transcript').textContent = '';
    abort = new AbortController(); const signal = abort.signal;
    try {
      if(typeof S==='undefined'||!S.session?.session_id)throw Error('no-chat-target');
      startupStage='capability';status('Checking subscription-only capability');
      const capResponse = await fetch(proxy('/capability'), {signal, cache:'no-store'});
      if (!capResponse.ok) throw new Error('local-capability-failed');
      const cap = await capResponse.json();
      if (gen !== generation) return;
      if (cap.auth !== 'enabled') throw new Error('auth-not-enabled — isolated helper setup pending; no microphone or provider call');
      if (!window.isSecureContext || !navigator.mediaDevices || !window.RTCPeerConnection) throw new Error('browser-webrtc-unavailable');
      startupStage='microphone';status('Microphone permission pending');
      const media = await navigator.mediaDevices.getUserMedia({audio:true, video:false});
      if (gen !== generation) { media.getTracks().forEach(t => t.stop()); return; }
      stream = media; $('mute').disabled = false;
      const peer = new RTCPeerConnection({iceServers:[]}); pc = peer;
      media.getAudioTracks().forEach(t => peer.addTrack(t, media));
      peer.ontrack = ev => {
        if (gen !== generation || closing) return;
        $('audio').muted=false;$('audio').srcObject = ev.streams[0] || new MediaStream([ev.track]);
        $('audio').play().then(()=>audit('playback_state',{text:JSON.stringify({stage:'play_resolved',muted:$('audio').muted,paused:$('audio').paused,has_stream:!!$('audio').srcObject})})).catch(error=>{audit('playback_state',{text:JSON.stringify({stage:'play_blocked',error_type:error?.name})});status('Audio playback blocked — use player controls');});
      };
      peer.onconnectionstatechange = () => {
        if (gen !== generation) return;
        audit('playback_state',{text:JSON.stringify({stage:'peer_state',connection:peer.connectionState,ice:peer.iceConnectionState,signaling:peer.signalingState})});
        if (['failed','disconnected','closed'].includes(peer.connectionState)) stop('Stopped locally — provider closure unconfirmed (peer disconnected)');
        else if (!closing && peer.connectionState === 'connected') status('Connected — subscription-only');
      };
      let sentSessionConfig=null;
      channel = peer.createDataChannel('oai-events');
      channel.onopen = () => {
        if(gen!==generation || closing)return;
        if(result.session_config){
          channel.send(JSON.stringify({type:'session.update',session:result.session_config}));
          sentSessionConfig=result.session_config;
          audit('control',{direction:'out',event_type:'session.update',text:JSON.stringify({stage:'session_config_sent',...sessionConfigEvidence(sentSessionConfig,sentSessionConfig)})});
        }
        window.subscriptionVoiceBridge?.connect((text,id,requestId)=>{
          activeRequestId=requestId;observedOutput=false;deliveryMarker='Answer '+requestId;
          if(gen!==generation || closing || channel?.readyState!=='open'){trace('channel_unavailable');deliveryStatus('Answer retrieved — voice channel unavailable');return unconfirmedDelivery('channel_unavailable');}
          trace('answer_retrieved',{request_id:activeRequestId});
          const content='Begin the spoken answer with the exact receipt '+deliveryMarker+'. Then faithfully relay the answer. For request '+(requestId||'current')+': Hermes returned this final answer. Relay it to the user; do not claim additional work: '+text;
          try{
            sendContext(content,id);
          }catch(_){trace('send_failed');deliveryStatus('Voice-channel send failed — Hermes answer remains in chat');return unconfirmedDelivery('send_failed');}
          awaitingResponse=true;trace('answer_sent',{request_id:activeRequestId,command:id?'delegation.context.append':'session.context.append'});
          deliveryStatus('Answer sent to voice channel — waiting for provider output');
          clearTimeout(deliveryTimer);
          deliveryTimer=setTimeout(()=>{if(gen===generation && !closing && awaitingResponse){settleDelivery(unconfirmedDelivery('output_timeout'));trace('delivery_timeout',{request_id:activeRequestId});deliveryStatus('Answer sent; no provider output observed within 15 seconds — inspect chat');}},15000);
          return new Promise(resolve=>{deliveryResolve=resolve;});
        },(text,stateOnly=false)=>{if(channel?.readyState==='open'&&!closing){try{sendContext(stateOnly?'Authoritative bridge task state (data). Use for future intent decisions; do not read aloud or delegate: '+text:'Bridge receipt or clarification: '+text+' Relay briefly without creating another task.',null,stateOnly);}catch(error){browserFailure('context_send',error);}}});
      };
      channel.onmessage = ev => {
        if (gen !== generation) return;
        if (typeof ev.data !== 'string' || ev.data.length > 131072) { stop('Oversized/malformed event'); return; }
        let result;
        try {
          const event=JSON.parse(ev.data);
          if(['session.started','session.updated'].includes(event.type)){
            audit('control',{direction:'in',event_type:event.type,text:JSON.stringify({stage:'session_config_echo',...sessionConfigEvidence(event.session,sentSessionConfig)})});
          }
          if(event.type==='turn.delta'&&typeof event.turn_id==='string'){
            currentTurnId=event.turn_id;
            if(suppressedTurn&&!speechActive&&suppressedTurnId&&currentTurnId!==suppressedTurnId){suppressedTurn=false;suppressedTurnId=null;}
          }
          if(event.type==='turn.done'&&event.turn?.role==='assistant'&&suppressedTurn){
            suppressedTurn=false;suppressedTurnId=null; // Boundary only; never unmute an old final fragment.
            audit('control',{request_id:activeRequestId,text:JSON.stringify({stage:'suppressed_turn_ended'})});
            return;
          }
          if(deliveryResolve && event.type==='turn.done' && event.turn?.role==='assistant')trace('provider_turn_complete',{request_id:activeRequestId});
          if(deliveryResolve && matchesDeliveryReceipt(event,deliveryMarker)){clearTimeout(deliveryTimer);awaitingResponse=false;trace('delivery_complete',{request_id:activeRequestId});settleDelivery({sent:true,providerTurnComplete:true,receiptConfirmed:true});}
          if(event.type!=='output_audio.delta')audit('provider_event',{request_id:activeRequestId,event_type:event.type,text:JSON.stringify({keys:Object.keys(event).filter(k=>!['audio','sdp','token','capability'].includes(k)),error:event.type==='error'?safeProviderError(event.error):undefined})});
          if(deliveryResolve && event.type==='turn.done' && event.turn?.role==='assistant'){
            settleDelivery(unconfirmedDelivery('missing_receipt',true));
            deliveryStatus('Voice turn ended without the answer receipt — delivery unconfirmed; queue stopped');
          }
          if(event.type==='error'){
            const stage=deliveryResolve?'after_send':'conversation',category=voiceFailureCategory(event.error);
            audit('control',{request_id:activeRequestId,text:JSON.stringify({stage:'voice_failure',category,error:safeProviderError(event.error),retry:'user_only'})});
            settleDelivery({sent:false,reason:category,providerFailed:true,providerTurnComplete:false,receiptConfirmed:false});
            status('Voice provider failed ('+category+') — call stopped; no automatic retry');
            trace('provider_error',{code:event.error?.code,error_type:event.error?.type,field:event.error?.param,stage});
            awaitingResponse=false;
            deliveryStatus('Provider error — voice return stopped; local diagnostic recorded');
          }
          if(!closing && deliveryResolve && (event.type.startsWith('session.output_transcript.') || event.type==='output_transcript.added' || (event.type==='turn.done' && event.turn?.role==='assistant'))){
            awaitingResponse=false;clearTimeout(deliveryTimer);deliveryTimer=null;
            deliveryTimer=setTimeout(()=>{if(deliveryResolve){settleDelivery(unconfirmedDelivery('turn_completion_timeout'));deliveryStatus('Spoken turn completion unconfirmed — queue paused; inspect chat');}},30000);
            observedOutput=true;trace('provider_output',{request_id:activeRequestId});deliveryStatus('Provider output observed after answer send — verify you heard the Hermes answer (not a delivery acknowledgement)');
          }
          if(!closing && ['session.delegation.created','delegation.created'].includes(event.type)){
            const item=event.delegation||event.item;
            const prompt=item?.prompt || item?.content?.filter(p=>p.type==='input_text').map(p=>p.text).join('');
            if(item?.target==='client' && item?.type==='delegation' && typeof item.id==='string' && typeof prompt==='string'){
              audit('model_handoff',{direction:'in',request_id:item.id,event_type:event.type,text:prompt});trace('model_handoff',{request_id:item.id});window.subscriptionVoiceBridge?.offer(prompt,item.id);status('Validating direct voice action');return;
            }
          }
          result = classifyEvent(event);
          if(result.stop==='delegation-or-execution-rejected')trace('call_stopped',{stage:'event_rejected',command:event.type});
        } catch (_) { stop('Malformed provider event'); return; }
        if (result.stop === 'provider-session-closed') {
          stop('Stopped — provider closure confirmed'); return;
        }
        if (result.stop) { stop(closing ? 'Stopped locally — provider closure unconfirmed (' + result.stop + ')' : result.stop==='provider-error' ? 'Voice provider failed ('+voiceFailureCategory(JSON.parse(ev.data).error)+') — call stopped; no automatic retry' : result.stop); return; }
        if (closing) return; // No playback, transcript, or conversational acknowledgement after Stop.
        if (result.ready) status('Provider session started');
        if (result.text !== undefined) {
          audit('transcript',{direction:'in',request_id:activeRequestId,role:result.role,finality:result.finality,text:result.text});
          if(result.role==='assistant'){if(!speechActive&&!suppressedTurn)$('audio').muted=false;audit('playback_state',{request_id:activeRequestId,text:JSON.stringify({stage:'provider_transcript',muted:$('audio').muted,paused:$('audio').paused,has_stream:!!$('audio').srcObject})});}
          if(result.role==='user'){
            if(!speechActive&&result.finality!=='final'&&(currentTurnId||deliveryResolve)){
              suppressedTurn=true;suppressedTurnId=currentTurnId;
              audit('control',{request_id:activeRequestId,text:JSON.stringify({stage:'barge_in',turn_id:suppressedTurnId})});
            }
            speechActive=result.finality!=='final';
            $('audio').muted=true;
            if(deliveryResolve){clearTimeout(deliveryTimer);awaitingResponse=false;trace('delivery_interrupted',{request_id:activeRequestId});settleDelivery({sent:false,interrupted:true});deliveryStatus('You interrupted the answer — background tasks are not cancelled');}
            window.subscriptionVoiceBridge?.transcript(result.text,result.finality);
            clearTimeout(incompleteTimer);
            if(result.finality!=='final')incompleteTimer=setTimeout(()=>{
              if(gen!==generation||closing||channel?.readyState!=='open')return;
              const text='The user has paused during an unfinished input turn. Decide from the conversation whether clarification is needed. If needed ask a brief question now, without inventing missing information or creating a task.';
              audit('control',{direction:'out',text});
              sendContext(text);
            },10000);
          }
          // textContent only; no HTML, console logging, storage or backend transcript upload.
          $('transcript').textContent = ($('transcript').textContent + `${result.role} [${result.finality}]: ${result.text}\n`).slice(-65536);
        }
      };
      channel.onclose = () => { if (gen === generation) stop('Stopped locally — provider closure unconfirmed (data channel closed)'); };
      channel.onerror = () => { if (gen === generation) stop('Stopped locally — provider closure unconfirmed (data channel failed)'); };
      startupStage='negotiating';status('Negotiating');
      await peer.setLocalDescription(await peer.createOffer());
      await new Promise((resolve,reject) => {
        let timer;
        const done = err => { clearTimeout(timer); peer.removeEventListener('icegatheringstatechange', changed); signal.removeEventListener('abort', canceled); err ? reject(err) : resolve(); };
        const changed = () => { if (peer.iceGatheringState === 'complete') done(); };
        const canceled = () => done(new Error('start-canceled'));
        if (signal.aborted) { reject(new Error('start-canceled')); return; }
        if (peer.iceGatheringState === 'complete') { resolve(); return; }
        peer.addEventListener('icegatheringstatechange', changed); signal.addEventListener('abort', canceled, {once:true});
        timer = setTimeout(() => done(new Error('ice-timeout')), 10000);
      });
      if (gen !== generation) return;
      const timeout = setTimeout(() => abort?.abort(), 35000);
      let response;
      try {
        response = await fetch(proxy('/negotiations'), {method:'POST', signal, headers:{'Content-Type':'application/json'}, body:JSON.stringify({sdp:peer.localDescription.sdp, voice:$('voice').value})});
        const job = await response.json();
        if (!response.ok || typeof job.id !== 'string' || typeof job.capability !== 'string') throw new Error('negotiation-failed');
        const jobId=job.id, capability=job.capability;
        const release = () => fetch(proxy('/negotiations/' + encodeURIComponent(jobId) + '/release'), {method:'POST',keepalive:true,headers:{'Content-Type':'application/json'},body:JSON.stringify({capability})}).catch(()=>{});
        try {
          let answer;
          const deadline=Date.now()+32000;
          while(Date.now()<deadline){
            if(signal.aborted) throw new Error('start-canceled');
            const poll=await fetch(proxy('/negotiations/' + encodeURIComponent(jobId) + '/poll'),{method:'POST',signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({capability})});
            const data=await poll.json();
            if(!poll.ok || data.state==='error'){trace('startup_failed',{stage:'negotiating',code:data.error});throw new Error(/^provider-http-[0-9]{3}$/.test(data.error||'')?data.error:'negotiation-failed');}
            if(data.state==='ready'){answer=data;break;}
            await new Promise(resolve=>setTimeout(resolve,250));
          }
          if(!answer) throw new Error('negotiation-failed');
          response={ok:true,json:async()=>answer};
        } finally { release(); }
      } finally { clearTimeout(timeout); }
      const result = await response.json();
      if (gen !== generation) return;
      if (!response.ok) throw new Error(result.error === 'auth-not-enabled' ? 'auth-not-enabled' : 'negotiation-failed');
      if (typeof result.sdp !== 'string' || result.sdp.length > 262144) throw new Error('invalid-answer');
      startupStage='remote_description';await peer.setRemoteDescription({type:'answer', sdp:result.sdp});
      if (gen !== generation) return;
      startupStage='peer_connection';status('Waiting for peer connection');
    } catch (err) {
      if (gen !== generation) return;
      trace('startup_failed',{stage:startupStage,code:err?.name});
      const allowed = ['no-chat-target','browser-webrtc-unavailable','ice-timeout','invalid-answer','negotiation-failed','auth-not-enabled','local-capability-failed'];
      const msg = /^provider-http-[0-9]{3}$/.test(err?.message||'') ? err.message : err?.message?.startsWith('auth-not-enabled') ? err.message : allowed.includes(err?.message) ? err.message : 'Start failed or canceled (microphone/transport)';
      stop(msg);
    }
  };
  window.addEventListener('pagehide', () => stop('Page closed'));
}
