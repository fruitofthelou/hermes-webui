"""Bounded local metadata trace. No conversation, SDP, or credentials."""
import json,re,threading,time
from collections import deque
from pathlib import Path
EVENTS={'call_started','call_stopped','answer_retrieved','answer_sent','send_failed','provider_output','provider_error','delivery_timeout','channel_unavailable','test_probe','startup_failed','negotiation_error','request_state','model_handoff','delivery_complete','routing_error','routing_started','routing_finished','routing_superseded','request_control','bridge_reset','handoff_error','browser_error','delivery_interrupted','delivery_unconfirmed','clarification_pending','clarification_answered'}
FIELDS={'code','error_type','command','stage','field','request_id','trace_session','route_id','handoff_id','job_id'}
class Diagnostics:
    def __init__(self,path):
        self.path=Path(path);self.lock=threading.Lock();self.rows=deque(maxlen=300)
        if self.path.exists() and self.path.stat().st_size<256000:
            for line in self.path.read_text(encoding='utf-8').splitlines()[-300:]:
                try:
                    row=json.loads(line)
                    if isinstance(row,dict) and row.get('event') in EVENTS:
                        clean={'event':row['event'],'time':row.get('time') if isinstance(row.get('time'),(int,float)) else time.time()}
                        for key in FIELDS:
                            value=row.get(key)
                            if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,80}',value):clean[key]=value
                        seq=row.get('client_sequence')
                        if isinstance(seq,int) and not isinstance(seq,bool) and 0<seq<10000000:clean['client_sequence']=seq
                        self.rows.append(clean)
                except (ValueError,TypeError):pass
    def append(self,data):
        if not isinstance(data,dict) or data.get('event') not in EVENTS:raise ValueError('invalid-event')
        row={'time':time.time(),'event':data['event']}
        for k in FIELDS:
            v=data.get(k)
            if isinstance(v,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,80}',v):row[k]=v
        seq=data.get('client_sequence')
        if isinstance(seq,int) and not isinstance(seq,bool) and 0<seq<10000000:row['client_sequence']=seq
        with self.lock:
            self.rows.append(row)
            self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            # Preserve the full test lifecycle; the bounded file remains the quick view.
            history=self.path.with_name('diagnostic-trace.history.jsonl')
            if history.exists() and history.stat().st_size>20*1024*1024:
                history.replace(self.path.with_name('diagnostic-trace.history-'+str(time.time_ns())+'.jsonl'))
            with history.open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
            self.path.write_text(''.join(json.dumps(r)+'\n' for r in self.rows),encoding='utf-8')
        return row
