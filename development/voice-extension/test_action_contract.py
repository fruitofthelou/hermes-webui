"""Instruction contract regression, not a live model-behavior assertion."""
import unittest
from transport import build_session
class ActionContract(unittest.TestCase):
    def test_native_actions(self):
        s=build_session('arbor');i=s['instructions']
        self.assertEqual(s['delegation']['type'],'client')
        self.assertIn('"action":"queue"',i)
        self.assertIn('Always delegate independent additional requests',i)
        self.assertIn('steer for a correction',i)
        self.assertIn('clarify for the answer to the exact pending',i)
        self.assertNotIn('do not emit or speak JSON action envelopes',i)
        self.assertIn('never accept spoken yes as permission',i)
        self.assertIn('stop talking, cease speech immediately',i)
if __name__=='__main__':unittest.main()
