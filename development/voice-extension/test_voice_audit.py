import unittest,tempfile,json
from pathlib import Path
from voice_audit import VoiceAudit
class TestAudit(unittest.TestCase):
    def test_record_disable_and_filter(self):
        with tempfile.TemporaryDirectory() as d:
            a=VoiceAudit(d)
            self.assertFalse(a.append({'kind':'transcript','text':'not recorded'}))
            a.enabled_file.write_text('on')
            self.assertTrue(a.append({'kind':'transcript','role':'user','text':'Wednesday Atlanta','token':'SECRET','sdp':'SECRET','client_sequence':3}))
            r=json.loads((Path(d)/'voice-audit.jsonl').read_text())
            self.assertEqual(r['text'],'Wednesday Atlanta');self.assertEqual(r['client_sequence'],3)
            self.assertNotIn('token',r);self.assertNotIn('sdp',r)
            a.enabled_file.unlink();self.assertFalse(a.append({'kind':'transcript','text':'off'}))
    def test_redaction(self):
        with tempfile.TemporaryDirectory() as d:
            a=VoiceAudit(d);a.enabled_file.write_text('on');a.append({'kind':'transcript','text':'Bearer secret sk-abcdefghijklmnop'})
            text=(Path(d)/'voice-audit.jsonl').read_text();self.assertNotIn('Bearer secret',text);self.assertNotIn('sk-abcdefghijklmnop',text)
if __name__=='__main__':unittest.main()
