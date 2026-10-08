import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from routing_diagnostics import RoutingDiagnostics,scrub
from intent_router import decide
from diagnostics import Diagnostics
from transport import ProbeError

class Tests(unittest.TestCase):
    def test_redaction_and_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'routing.jsonl';log=RoutingDiagnostics(p)
            log.append('test',authorization='secret',input={'api_key':'secret','text':'Bearer secret sk-abcdefghijklmnop password=secret'},route_id='route-test')
            raw=p.read_text();self.assertNotIn('secret',raw);self.assertIn('route-test',raw)
            self.assertEqual(json.loads(raw)['event'],'test')
    def test_routing_error_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            log=Diagnostics(Path(d)/'trace.jsonl')
            self.assertEqual(log.append({'event':'routing_error','route_id':'route-test','code':'routing-invalid-json'})['route_id'],'route-test')
    def run_model(self,output=None,error=None):
        events=[]
        client=NS(close=lambda:None,chat=NS(completions=NS(create=lambda **kw:None)))
        def create(**kw):
            if error:raise error
            return NS(choices=[NS(message=NS(content=output),finish_reason='stop')],_request_id='provider-test')
        client.chat.completions.create=create
        data={'provider':'openrouter','model':'test','conversation':[],'state':{},'fragment':'test'}
        with patch('hermes_cli.runtime_provider.resolve_runtime_provider',return_value={'api_key':'synthetic'}),patch('openai.OpenAI',return_value=client):
            try:result=decide(data,diagnostic=lambda event,**kw:events.append({'event':event,**kw}))
            except ProbeError as exc:result=exc.code
        return result,events
    def test_success_captured(self):
        result,events=self.run_model('{"action":"queue","text":"hands-free request worked","reason":"test"}')
        self.assertEqual(result['action'],'queue')
        self.assertEqual(events[-1]['event'],'decision_validated')
        self.assertIn('provider_response',[e['event'] for e in events])
    def test_invalid_json_captured(self):
        result,events=self.run_model('not json')
        self.assertEqual(result,'routing-invalid-json');self.assertEqual(events[-1]['stage'],'response_parse')
        self.assertEqual(events[-2]['output'],'not json')
    def test_invalid_decision_captured(self):
        result,events=self.run_model('{"action":"queue","text":"","reason":"test"}')
        self.assertEqual(result,'invalid-routing-decision');self.assertEqual(events[-1]['stage'],'decision_validation')
    def test_timeout_captured(self):
        class SyntheticTimeout(Exception):pass
        result,events=self.run_model(error=SyntheticTimeout('do not log secret'))
        self.assertEqual(result,'routing-provider-timeout');self.assertEqual(events[-1]['error_type'],'SyntheticTimeout')
        self.assertNotIn('secret',json.dumps(events))
    def test_provider_http_captured(self):
        class Rejection(Exception):status_code=429
        result,events=self.run_model(error=Rejection())
        self.assertEqual(events[-1]['http_status'],429)

if __name__=='__main__':unittest.main()
