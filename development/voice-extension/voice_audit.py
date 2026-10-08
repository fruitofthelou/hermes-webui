"""Explicitly authorized temporary local text audit, never raw protocol payloads."""
import json,re,threading,time
from pathlib import Path
KINDS={'transcript','model_handoff','draft','confirmed_request','hermes_answer','voice_send','control','routing_decision','routing_lifecycle','browser_error','provider_event','playback_state','task_failure'}
class VoiceAudit:
    def __init__(self,directory):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.enabled_file=self.directory/'enabled';self.lock=threading.Lock()
    @property
    def enabled(self):return self.enabled_file.exists()
    def append(self,data):
        if not self.enabled:return False
        if not isinstance(data,dict) or data.get('kind') not in KINDS:raise ValueError('invalid-audit')
        row={'time':time.time(),'kind':data['kind']}
        for key in ('direction','role','event_type','finality','request_id','trace_session','route_id','handoff_id'):
            value=data.get(key)
            if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.: ()-]{1,100}',value):row[key]=value
        text=data.get('text')
        if text is not None:
            if not isinstance(text,str) or len(text)>65536:raise ValueError('invalid-text')
            # Redact common credential patterns if accidentally dictated.
            text=re.sub(r'(?i)\bBearer\s+\S+','Bearer [REDACTED]',text)
            text=re.sub(r'\b(?:sk-[A-Za-z0-9_-]{12,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)','[REDACTED]',text)
            from routing_diagnostics import scrub
            row['text']=scrub(text)
        seq=data.get('client_sequence')
        if isinstance(seq,int) and not isinstance(seq,bool) and 0<seq<10000000:row['client_sequence']=seq
        with self.lock:
            path=self.directory/'voice-audit.jsonl'
            if path.exists() and path.stat().st_size>20*1024*1024:
                path.replace(self.directory/('voice-audit-'+str(time.time_ns())+'.jsonl'))
            with path.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        return True
