import unittest,json,tempfile,time,threading
from pathlib import Path
from helper import make_app,Jobs
from transport import ProbeError
SDP='v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n'
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.app=make_app(lambda s,v:{'sdp':SDP});self.app._token_path=Path(self.tmp.name)/'token';self.app._token_path.write_text('synthetic-test-token');self.headers={'X-Hermes-Sidecar-Token':'synthetic-test-token','Content-Type':'application/json'}
 def tearDown(self): self.tmp.cleanup()
 def request(self,path,data=None,headers=None,method='POST'):
  r=self.app._dispatch(method,path,headers if headers is not None else self.headers,lambda:json.dumps(data).encode());return r[0],json.loads(r[2])
 def test_health(self): self.assertEqual(self.request('/health',headers={},method='GET')[0],200)
 def test_missing_token(self): self.assertEqual(self.request('/capability',headers={},method='GET')[0],401)
 def test_wrong_token(self): self.assertEqual(self.request('/capability',headers={'X-Hermes-Sidecar-Token':'bad'},method='GET')[0],401)
 def test_absent_file(self):
  self.app._token_path.unlink();self.assertEqual(self.request('/capability',method='GET')[0],503)
 def test_capability_disabled(self): self.assertEqual(self.request('/capability',method='GET')[1]['auth'],'auth-not-enabled')
 def test_job_roundtrip(self):
  status,j=self.request('/negotiations',{'sdp':SDP,'voice':'arbor'});self.assertEqual(status,202)
  for _ in range(100):
   status,r=self.request('/negotiations/'+j['id']+'/poll',{'capability':j['capability']})
   if r['state']!='pending':break
   time.sleep(.002)
  self.assertEqual(r['sdp'],SDP);self.assertNotIn('cap',r)
  self.assertEqual(r['session_config']['delegation'],{'type':'client'})
  self.assertNotIn('model',r['session_config'])
  self.assertNotIn('MUST be a JSON',r['session_config']['instructions'])
  self.assertEqual(self.request('/negotiations/'+j['id']+'/poll',{'capability':'wrong'})[0],404)
  self.assertEqual(self.request('/negotiations/'+j['id']+'/release',{'capability':j['capability']})[0],200)
  self.assertEqual(self.request('/negotiations/'+j['id']+'/poll',{'capability':j['capability']})[0],404)
 def test_bad_body(self): self.assertEqual(self.request('/negotiations',{'sdp':'bad','voice':'arbor'})[0],400)
 def test_expiry(self):
  clock=[0];jobs=Jobs(lambda s,v:{'sdp':SDP},lambda:clock[0]);j=jobs.create(SDP,'arbor');clock[0]=91
  with self.assertRaises(ProbeError): jobs.get(j['id'],j['capability'])
 def test_cancel_pending(self):
  gate=threading.Event();jobs=Jobs(lambda s,v:(gate.wait(1) or True) and {'sdp':SDP});j=jobs.create(SDP,'arbor');jobs.get(j['id'],j['capability'],True);gate.set();time.sleep(.02);self.assertNotIn(j['id'],jobs.jobs)
 def test_busy(self):
  gate=threading.Event();jobs=Jobs(lambda s,v:(gate.wait(1) or True) and {'sdp':SDP});jobs.create(SDP,'arbor');jobs.create(SDP,'arbor')
  try:
   with self.assertRaises(ProbeError):jobs.create(SDP,'arbor')
  finally:gate.set()
 def test_real_transport_disabled(self):
  jobs=Jobs();j=jobs.create(SDP,'arbor')
  for _ in range(100):
   r=jobs.get(j['id'],j['capability'])
   if r['state']!='pending':break
   time.sleep(.002)
  self.assertEqual(r['error'],'auth-not-enabled')
if __name__=='__main__':unittest.main()
