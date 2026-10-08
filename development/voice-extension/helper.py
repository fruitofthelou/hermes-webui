"""Voice-only jobs behind canonical token-v1 dispatch. No agent execution."""
import json
import secrets
import threading
import time
import hmac
from pathlib import Path
from sidecar_base import Sidecar
from transport import negotiate, DisabledAuth, ProbeError, validate_sdp, build_session, MAX_BODY

class Jobs:
    def __init__(self, provider=None, clock=time.monotonic):
        self.provider = provider or (lambda s,v: negotiate(s,v,DisabledAuth()))
        self.clock=clock
        self.lock=threading.Lock()
        self.jobs={}
        self.active=0
    def purge(self):
        self.jobs={k:v for k,v in self.jobs.items() if v['expires']>self.clock()}
    def create(self,sdp,voice):
        validate_sdp(sdp); build_session(voice)
        with self.lock:
            self.purge()
            if self.active>=2 or len(self.jobs)>=8: raise ProbeError('busy',409)
            key=secrets.token_urlsafe(24);cap=secrets.token_urlsafe(32)
            job={'cap':cap,'expires':self.clock()+90,'state':'pending'}
            self.jobs[key]=job;self.active+=1
        def run():
            try:
                result=self.provider(sdp,voice)
                validate_sdp(result['sdp'])
                # Preserve the contract used for negotiation, rather than silently
                # rebuilding potentially different instructions at the second hop.
                config=result['session_config'] if 'session_config' in result else build_session(voice)
                if not isinstance(config,dict) or not isinstance(config.get('instructions'),str):
                    raise ProbeError('invalid-session-config')
                outcome={'state':'ready','sdp':result['sdp'],
                         'session_config':{k:v for k,v in config.items() if k!='model'}}
            except ProbeError as e: outcome={'state':'error','error':e.code}
            except Exception: outcome={'state':'error','error':'negotiation-failed'}
            with self.lock:
                self.active-=1
                if self.jobs.get(key) is job and job['expires']>self.clock(): job.update(outcome)
        threading.Thread(target=run,daemon=True).start()
        return {'id':key,'capability':cap}
    def get(self,key,cap,delete=False):
        with self.lock:
            self.purge();j=self.jobs.get(key)
            if not j or not isinstance(cap,str) or not hmac.compare_digest(cap,j['cap']): raise ProbeError('job-not-found',404)
            if delete:
                del self.jobs[key];return {'state':'released'}
            return {k:v for k,v in j.items() if k not in ('cap','expires')}

def make_app(provider=None, auth=None, state_dir=None, port=None, token_file=None):
    auth=auth or DisabledAuth()
    from diagnostics import Diagnostics
    from voice_state import state_directory, NullSink
    state=state_directory(state_dir)
    trace=Diagnostics(state/'diagnostic-trace.jsonl') if state else NullSink()
    def diagnosed_provider(s,v):
        try:return (provider or (lambda s,v: negotiate(s,v,auth)))(s,v)
        except ProbeError as e:
            trace.append({'event':'negotiation_error','code':e.code,'stage':'helper'})
            raise
    app=Sidecar(str(Path(__file__).with_name('sidecar.json')));jobs=Jobs(diagnosed_provider)
    if port is not None:
        if isinstance(port,bool) or not isinstance(port,int) or not 1<=port<=65535:raise ValueError('invalid loopback port')
        app.port=port
    if token_file is not None:app._token_path=Path(token_file)
    def body(req,keys):
        if req.headers.get('Content-Type')!='application/json' or len(req.body)>MAX_BODY: raise ProbeError('invalid-body',400)
        try: d=json.loads(req.body)
        except Exception: raise ProbeError('invalid-json',400)
        if not isinstance(d,dict) or set(d)!=set(keys): raise ProbeError('invalid-request',400)
        return d
    def guarded(fn):
        def wrapped(req):
            try:
                status,headers,b=fn(req)
                headers['Cache-Control']='no-store'
                return status,headers,b
            except ProbeError as e: return app.json({'error':e.code},e.status)
        return wrapped
    @app.route('GET','/capability')
    def capability(req):
        try:
            auth.load();state='enabled'
        except ProbeError as e:state=e.code
        return app.json({'auth':state,'lane':'subscription-only','executor':False})
    @app.route('POST','/negotiations')
    @guarded
    def create(req):
        d=body(req,['sdp','voice']);return app.json(jobs.create(d['sdp'],d['voice']),202)
    @app.route('POST','/negotiations/{id}/poll')
    @guarded
    def poll(req):
        d=body(req,['capability']);return app.json(jobs.get(req.params['id'],d['capability']))
    @app.route('POST','/negotiations/{id}/release')
    @guarded
    def release(req):
        d=body(req,['capability']);return app.json(jobs.get(req.params['id'],d['capability'],True))
    @app.route('POST','/diagnostics')
    @guarded
    def diagnostic(req):
        if len(req.body)>1024:raise ProbeError('invalid-body',400)
        try:trace.append(json.loads(req.body))
        except (ValueError,TypeError):raise ProbeError('invalid-diagnostic',400)
        return app.json({'recorded':True})
    from voice_audit import VoiceAudit
    audit=VoiceAudit(state/'voice-audit') if state else NullSink()
    @app.route('POST','/audit')
    @guarded
    def audit_write(req):
        if req.headers.get('Content-Type')!='application/json' or len(req.body)>400000:raise ProbeError('invalid-body',400)
        try:recorded=audit.append(json.loads(req.body))
        except (ValueError,TypeError):raise ProbeError('invalid-audit',400)
        return app.json({'recorded':recorded,'enabled':audit.enabled})
    from routing_diagnostics import RoutingDiagnostics, exception_evidence
    routing_log=RoutingDiagnostics(state/'voice-audit'/'routing-diagnostics.jsonl') if state else NullSink()
    decisions={};decision_lock=threading.Lock()
    @app.route('POST','/decisions')
    @guarded
    def decision(req):
        if req.headers.get('Content-Type')!='application/json' or len(req.body)>100000:raise ProbeError('invalid-body',400)
        raise ProbeError('secondary-interpreter-removed',410)
    @app.route('POST','/decisions/{id}/poll')
    @guarded
    def decision_poll(req):
        data=body(req,['capability'])
        with decision_lock:
            job=decisions.get(req.params['id'])
            if not job or job['expires']<time.monotonic() or not isinstance(data['capability'],str) or not hmac.compare_digest(data['capability'],job['cap']):raise ProbeError('decision-not-found',404)
            routing_log.append('job_polled',job_id=req.params['id'],state=job['state'])
            return app.json({k:v for k,v in job.items() if k not in ('cap','expires')})
    return app

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--readonly-codex-login',action='store_true')
    parser.add_argument('--lb-key-file')
    parser.add_argument('--port',type=int)
    parser.add_argument('--token-file')
    parser.add_argument('--state-dir')
    args=parser.parse_args()
    from voice_state import state_directory
    state=state_directory(args.state_dir,required=True)
    options={'state_dir':state,'port':args.port,'token_file':args.token_file}
    auth=DisabledAuth()
    if args.readonly_codex_login:
        from codex_readonly_auth import ReadOnlyCodexAuth
        auth=ReadOnlyCodexAuth()
    if args.lb_key_file:
        if args.readonly_codex_login:raise SystemExit('Choose only one authentication route')
        from lb_auth import LocalLBAuth
        auth=LocalLBAuth(args.lb_key_file)
        url='http://localhost:2455/backend-api/codex/realtime/calls?intent=quicksilver&architecture=avas'
        make_app(auth=auth,provider=lambda s,v:negotiate(s,v,auth,call_url=url),**options).serve()
    else:make_app(auth=auth,**options).serve()
