import unittest
from intent_router import validate
from transport import ProbeError

class RoutingContractTests(unittest.TestCase):
    def test_status_without_text_uses_bridge_state(self):
        decision={'action':'status','text':'','reason':'Progress question'}
        self.assertEqual(validate(decision),decision)
    def test_execution_and_clarification_require_text(self):
        for action in ('queue','steer','stop','revise','rephrase','clarify'):
            with self.subTest(action=action),self.assertRaises(ProbeError):
                validate({'action':action,'text':'','reason':'test'})
    def test_exact_phrase_is_preserved(self):
        decision={'action':'queue','text':'Reply with exactly the hands-free request worked','reason':'New request'}
        self.assertEqual(validate(decision)['text'],decision['text'])
    def test_extra_fields_are_rejected(self):
        with self.assertRaises(ProbeError):
            validate({'action':'status','text':'','reason':'test','execute':True})

if __name__=='__main__':unittest.main()
