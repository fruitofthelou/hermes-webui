"""Offline negotiation config continuity; no credentials or provider calls."""
import threading
import unittest
from helper import Jobs

SDP = 'v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n'

class SessionConfigDelivery(unittest.TestCase):
    def ready(self, provider):
        done = threading.Event()
        jobs = Jobs(provider)
        job = jobs.create(SDP, 'arbor')
        # Acquire the real job lock while polling; no server or live state.
        for _ in range(100):
            result = jobs.get(job['id'], job['capability'])
            if result['state'] != 'pending':
                return result
            done.wait(.002)
        self.fail('offline job failed to settle')

    def test_preserve_transport_config_without_mutation(self):
        config = {'model': 'test-model', 'instructions': 'transport-specific-contract',
                  'audio': {'output': {'voice': 'arbor'}},
                  'delegation': {'type': 'client', 'ack_filler': False}}
        result = self.ready(lambda s, v: {'sdp': SDP, 'session_config': config})
        self.assertEqual(result['state'], 'ready')
        self.assertEqual(result['session_config'], {k: v for k, v in config.items() if k != 'model'})
        self.assertIn('model', config)

    def test_legacy_provider_without_config(self):
        result = self.ready(lambda s, v: {'sdp': SDP})
        self.assertEqual(result['session_config']['delegation'], {'type': 'client'})
        self.assertNotIn('model', result['session_config'])

    def test_invalid_explicit_config_fails_closed(self):
        result = self.ready(lambda s, v: {'sdp': SDP, 'session_config': None})
        self.assertEqual(result['state'], 'error')

if __name__ == '__main__':
    unittest.main()
