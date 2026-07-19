import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "test"))

from e2e_ai_motion_perf import (  # noqa: E402
    baseline_is_writable,
    exit_code_for_status,
    resolve_scenario_status,
    select_campaign_history,
)


class MotionProbeFlowTests(unittest.TestCase):
    def test_absolute_warning_is_not_hidden_by_baseline_or_clean_comparison(self):
        self.assertEqual(
            resolve_scenario_status(
                quality_status="warn",
                comparison_status=None,
                creating_baseline=True,
            ),
            "warn",
        )
        self.assertEqual(
            resolve_scenario_status(
                quality_status="warn",
                comparison_status="pass",
                creating_baseline=False,
            ),
            "warn",
        )

    def test_incompatible_comparison_is_invalid_and_severe_comparison_wins(self):
        self.assertEqual(
            resolve_scenario_status(
                quality_status="pass",
                comparison_status="incompatible",
                creating_baseline=False,
            ),
            "invalid",
        )
        self.assertEqual(
            resolve_scenario_status(
                quality_status="pass",
                comparison_status="fail",
                creating_baseline=False,
            ),
            "fail",
        )

    def test_invalid_or_fatal_baseline_is_never_written(self):
        self.assertTrue(
            baseline_is_writable(
                {
                    "scenarios": {
                        "off": {"status": "baseline"},
                        "on": {"status": "warn"},
                    }
                }
            )
        )
        self.assertFalse(
            baseline_is_writable(
                {"scenarios": {"off": {"status": "invalid"}}}
            )
        )
        self.assertFalse(
            baseline_is_writable(
                {"scenarios": {"off": {"status": "fail"}}}
            )
        )
        self.assertEqual(exit_code_for_status("fail"), 2)
        self.assertEqual(exit_code_for_status("invalid"), 2)
        self.assertEqual(exit_code_for_status("warn"), 0)

    def test_history_is_limited_to_the_current_campaign(self):
        history = [
            {"campaignId": "old", "status": "fail"},
            {"campaignId": "current", "status": "baseline", "isBaseline": True},
            {"campaignId": "current", "status": "pass"},
        ]
        self.assertEqual(
            select_campaign_history(history, "current"),
            history[1:],
        )


if __name__ == "__main__":
    unittest.main()
