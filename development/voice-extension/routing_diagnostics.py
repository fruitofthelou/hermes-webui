"""Local, bounded routing evidence. Never persist auth objects or HTTP headers."""
import json,re,time,threading,traceback
from pathlib import Path

def scrub(value):
    if isinstance(value,dict):
        return {str(k):('[REDACTED]' if re.search(r'(?i)token|secret|password|authorization|cookie|api.?key|capability|sdp',str(k)) else scrub(v)) for k,v in value.items()}
    if isinstance(value,list):return [scrub(v) for v in value]
    if isinstance(value,str):
        value=re.sub(r'(?i)\bBearer\s+\S+','Bearer [REDACTED]',value)
        value=re.sub(r'\b(?:sk-[A-Za-z0-9_-]{12,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)','[REDACTED]',value)
        value=re.sub(r'(?i)((?:api[_ -]?key|password|secret|access_token|refresh_token)\s*[=:]\s*)[^\s,;]+',r'\1[REDACTED]',value)
        return value[:100000]
    if value is None or isinstance(value,(bool,int,float)):return value
    return type(value).__name__

class RoutingDiagnostics:
    def __init__(self,path):self.path=Path(path);self.lock=threading.Lock()
    def append(self,event,**fields):
        row={'time':time.time(),'event':event,**scrub(fields)}
        with self.lock:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            if self.path.exists() and self.path.stat().st_size>10*1024*1024:
                previous=self.path.with_suffix('.previous.jsonl')
                self.path.replace(previous)
            with self.path.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        return row

def exception_evidence(exc):
    # Stack frames, not locals, headers, request objects, or provider response bodies.
    return {'error_type':type(exc).__name__,'http_status':getattr(exc,'status_code',None),
            'stack':[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)],
            'code':getattr(exc,'code',None)}
