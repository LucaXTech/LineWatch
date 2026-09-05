import unittest
from pathlib import Path

import dashboard


class DashboardTests(unittest.TestCase):
    def test_fmt_duration(self):
        self.assertEqual(dashboard.fmt_duration(None), "-")
        self.assertEqual(dashboard.fmt_duration(42), "42s")
        self.assertEqual(dashboard.fmt_duration(125), "2m 5s")
        self.assertEqual(dashboard.fmt_duration(3661), "1h 1m 1s")

    def test_percentile(self):
        self.assertIsNone(dashboard.percentile([], 0.95))
        self.assertEqual(dashboard.percentile([10], 0.95), 10)
        self.assertAlmostEqual(dashboard.percentile([1, 2, 3, 4], 0.5), 2.5)

    def test_uplinkwitness_dashboard_branding(self):
        template = (Path(__file__).resolve().parents[1] / "templates" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("<title>UplinkWitness</title>", template)
        self.assertIn("<h1>UplinkWitness</h1>", template)
        self.assertNotIn("<h1>LineWatch</h1>", template)


if __name__ == "__main__":
    unittest.main()
