"""Test deserializing."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
#pylint: disable=wrong-import-position
import deserialize
#pylint: enable=wrong-import-position


class SampleItem:
    """Sample item for use in tests."""
    field_1: int
    field_2: int

class DeserializationNonStrictTestSuite(unittest.TestCase):
    """Deserialization ignore test cases."""

    def test_keys(self):
        """Test that root lists deserialize correctly."""

        data = {
            "field_1": 1,
        }

        instance = deserialize.deserialize(SampleItem, data, strict=False)
        self.assertEqual(data["field_1"], instance.field_1)
