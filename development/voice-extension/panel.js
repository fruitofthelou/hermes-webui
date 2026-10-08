'use strict';
(() => {
  if (!window.hermesExt?.register('subscription-voice')) return;
  const host=document.getElementById('composerWrap');
  if(!host)throw new Error('voice-composer-mount-unavailable');
  const scope='subscription-voice-';
  const panel=document.createElement('details');panel.id=scope+'panel';
  const title=document.createElement('summary');title.textContent='Live voice';title.setAttribute('aria-label','Live voice controls — preview');panel.append(title);
  const body=document.createElement('div');body.className='voice-surface';panel.append(body);
  const row=document.createElement('div');row.className='voice-controls';body.append(row);
  for(const [id,text] of [['start','Start voice'],['mute','Mute mic'],['stop','End call']]){
    const b=document.createElement('button');b.id=scope+id;b.type='button';b.textContent=text;b.disabled=id!=='start';row.append(b);
  }
  const voice=document.createElement('select');voice.id=scope+'voice';voice.setAttribute('aria-label','Speaking voice');
  for(const name of ['cove']){const o=document.createElement('option');o.value=name;o.textContent=name;voice.append(o);}voice.hidden=true;row.append(voice);
  const status=document.createElement('p');status.id=scope+'status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');status.textContent='Ready · hands-free requests; approvals stay in chat';body.append(status);
  const notice=document.createElement('p');notice.className='voice-note';notice.textContent='Preview · Ending the call does not cancel Hermes work. Delivery unconfirmed means the answer stays in chat and the queue pauses, not that Hermes failed. Approvals stay in chat.';body.append(notice);
  const handoff=document.createElement('div');handoff.id=scope+'handoff';body.append(handoff);
  const qc=document.createElement('details');qc.className='voice-diagnostics';
  const qcTitle=document.createElement('summary');qcTitle.textContent='Diagnostics';qc.append(qcTitle);
  const diagnostic=document.createElement('p');diagnostic.id=scope+'delivery';qc.append(diagnostic);
  const audio=document.createElement('audio');audio.id=scope+'audio';audio.controls=true;qc.append(audio);
  const transcript=document.createElement('pre');transcript.id=scope+'transcript';qc.append(transcript);qc.hidden=true;body.append(qc);
  host.prepend(panel);
})();
