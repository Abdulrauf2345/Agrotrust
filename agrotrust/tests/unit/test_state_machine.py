import unittest

from agrotrust.shared.errors import InvalidStateTransition
from agrotrust.shared.state_machine import StateMachine


class StateMachineTests(unittest.TestCase):
    def setUp(self):
        self.m = StateMachine("t", {"A": ["B"], "B": ["C", "A"]})

    def test_valid(self):
        self.m.assert_can("A", "B")
        self.assertTrue(self.m.can("B", "C"))

    def test_invalid_rejected_with_details(self):
        with self.assertRaises(InvalidStateTransition) as ctx:
            self.m.assert_can("A", "C")
        self.assertEqual(ctx.exception.details["allowed"], ["B"])

    def test_terminal_and_unknown(self):
        self.assertTrue(self.m.is_terminal("C"))
        with self.assertRaises(InvalidStateTransition):
            self.m.can("ZZZ", "A")

    def test_mermaid(self):
        self.assertIn("A --> B", self.m.as_mermaid())


if __name__ == "__main__":
    unittest.main()
