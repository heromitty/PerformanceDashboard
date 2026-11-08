import unittest


class TestRemoteConnection(unittest.TestCase):
    def test_normalizes_connection_name(self):
        value = "  Remote Connection  "

        self.assertEqual(value.strip().lower().replace(" ", "_"), "remote_connection")


if __name__ == "__main__":
    unittest.main()
