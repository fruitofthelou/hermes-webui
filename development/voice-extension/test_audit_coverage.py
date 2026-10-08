import json,tempfile,unittest
from pathlib import Path
from diagnostics import Diagnostics
from voice_audit import VoiceAudit
class Coverage(unittest.TestCase):
    def test_history_survives_quick_view_eviction(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'diagnostic-trace.jsonl';log=Diagnostics(p)
            for i in range(305):log.append({'event':'provider_output','trace_session':'coverage','client_sequence':i+1,'authorization':'SECRET'})
            self.assertEqual(len(p.read_text().splitlines()),300)
            history=p.with_name('diagnostic-trace.history.jsonl').read_text()
            self.assertEqual(len(history.splitlines()),305);self.assertNotIn('SECRET',history)
    def test_new_audit_categories_redacted(self):
        with tempfile.TemporaryDirectory() as d:
            a=VoiceAudit(d);a.enabled_file.touch()
            for kind in ('provider_event','playback_state','task_failure'):
                a.append({'kind':kind,'text':'Bearer private-secret api_key=private-key','trace_session':'coverage'})
            text=(Path(d)/'voice-audit.jsonl').read_text();self.assertNotIn('private-secret',text);self.assertNotIn('private-key',text)
if __name__=='__main__':unittest.main()
