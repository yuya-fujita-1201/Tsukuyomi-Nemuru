import unittest
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.motion_metrics import (
    aggregate_motion_reports,
    compare_motion_reports,
    decide_loop_action,
    evaluate_motion_report,
    percentile,
    summarize_motion_samples,
)


def sample(at_ms, interval_ms, body_position, head_position=0.0, **overrides):
    return {
        "atMs": at_ms,
        "frameIntervalMs": interval_ms,
        "cueIndex": 0,
        "bodyFramePosition": body_position,
        "headFramePosition": head_position,
        "blink": 0.0,
        **overrides,
    }


class MotionMetricsTests(unittest.TestCase):
    def test_percentile_interpolates_and_rejects_noisy_values(self):
        values = [10, 20, float("nan"), -1, 30, 40]
        self.assertEqual(percentile(values, 0), 10)
        self.assertEqual(percentile(values, 50), 25)
        self.assertEqual(percentile(values, 100), 40)

    def test_summary_reports_frame_pacing_and_visible_key_skips(self):
        samples = [
            sample(0, 16, 0.0),
            sample(16, 17, 0.7),
            sample(50, 34, 2.2),
            sample(102, 52, 4.6),
        ]

        summary = summarize_motion_samples(samples, long_tasks=[55.0, 80.0])

        self.assertEqual(summary["frameCount"], 4)
        self.assertEqual(summary["frameIntervals"]["over33MsCount"], 2)
        self.assertEqual(summary["frameIntervals"]["over50MsCount"], 1)
        self.assertEqual(summary["longTasks"]["count"], 2)
        self.assertAlmostEqual(summary["bodyMotion"]["maxFrameStep"], 2.4)
        self.assertEqual(summary["bodyMotion"]["skipCount"], 2)

    def test_motion_summary_does_not_count_front_or_direction_changes_as_skips(self):
        samples = [
            sample(
                0,
                16,
                -2.0,
                -1.0,
                bodyActive=True,
                bodyDirection=-1,
                headActive=True,
                headDirection=-1,
            ),
            sample(
                16,
                16,
                0.0,
                0.0,
                bodyActive=False,
                bodyDirection=-1,
                headActive=False,
                headDirection=-1,
            ),
            sample(
                32,
                16,
                2.0,
                2.0,
                bodyActive=True,
                bodyDirection=1,
                headActive=True,
                headDirection=1,
            ),
            sample(
                48,
                16,
                3.2,
                2.8,
                bodyActive=True,
                bodyDirection=1,
                headActive=True,
                headDirection=1,
            ),
        ]

        summary = summarize_motion_samples(samples)

        self.assertAlmostEqual(summary["bodyMotion"]["maxFrameStep"], 1.2)
        self.assertEqual(summary["bodyMotion"]["skipCount"], 1)
        self.assertAlmostEqual(summary["headMotion"]["maxFrameStep"], 0.8)
        self.assertEqual(summary["headMotion"]["skipCount"], 0)

        legacy = summarize_motion_samples(
            [sample(0, 16, -2.0), sample(16, 16, 0.0), sample(32, 16, 2.0)]
        )
        self.assertEqual(legacy["bodyMotion"]["maxFrameStep"], 2.0)
        self.assertEqual(legacy["bodyMotion"]["skipCount"], 2)

    def test_summary_reports_tracking_error_and_settle_latency_per_axis(self):
        samples = [
            sample(
                0,
                16,
                0,
                0,
                targetTurn=0,
                currentTurn=0,
                bodyActive=False,
                bodySettled=True,
                targetHeadTurn=0,
                currentHeadTurn=0,
                headActive=False,
                headSettled=True,
            ),
            sample(
                100,
                16,
                1,
                1,
                cueIndex=1,
                targetTurn=1,
                currentTurn=0,
                bodyActive=True,
                bodySettled=False,
                targetHeadTurn=0.5,
                currentHeadTurn=0,
                headActive=True,
                headSettled=False,
            ),
            sample(
                200,
                16,
                2,
                2,
                cueIndex=1,
                targetTurn=1,
                currentTurn=0.4,
                bodyActive=True,
                bodySettled=False,
                targetHeadTurn=0.5,
                currentHeadTurn=0.3,
                headActive=True,
                headSettled=False,
            ),
            sample(
                400,
                16,
                3,
                3,
                cueIndex=1,
                targetTurn=1,
                currentTurn=0.9,
                bodyActive=True,
                bodySettled=True,
                targetHeadTurn=0.5,
                currentHeadTurn=0.5,
                headActive=False,
                headSettled=False,
            ),
            sample(
                500,
                16,
                2,
                2,
                cueIndex=2,
                targetTurn=0,
                currentTurn=0.8,
                bodyActive=True,
                bodySettled=False,
                targetHeadTurn=0,
                currentHeadTurn=0.4,
                headActive=True,
                headSettled=False,
            ),
            sample(
                700,
                16,
                0,
                0,
                cueIndex=2,
                targetTurn=0,
                currentTurn=0,
                bodyActive=False,
                bodySettled=False,
                targetHeadTurn=0,
                currentHeadTurn=0,
                headActive=False,
                headSettled=False,
            ),
            sample(
                800,
                16,
                1,
                1,
                cueIndex=3,
                targetTurn=1,
                currentTurn=0,
                bodyActive=True,
                bodySettled=False,
                targetHeadTurn=0.5,
                currentHeadTurn=0,
                headActive=True,
                headSettled=False,
            ),
        ]

        summary = summarize_motion_samples(samples)

        self.assertEqual(summary["bodyMotion"]["trackingError"]["unit"], "turn")
        self.assertEqual(summary["bodyMotion"]["settleLatency"]["unit"], "ms")
        self.assertEqual(summary["bodyMotion"]["trackingError"]["sampleCount"], 7)
        self.assertEqual(summary["bodyMotion"]["trackingError"]["max"], 1.0)
        self.assertEqual(summary["bodyMotion"]["trackingError"]["p95"], 1.0)
        self.assertEqual(summary["bodyMotion"]["settleLatency"]["sampleCount"], 2)
        self.assertEqual(summary["bodyMotion"]["settleLatency"]["p95Ms"], 295.0)
        self.assertEqual(summary["bodyMotion"]["settleLatency"]["maxMs"], 300.0)
        self.assertEqual(summary["bodyMotion"]["settleLatency"]["incompleteCount"], 1)
        self.assertEqual(summary["headMotion"]["settleLatency"]["sampleCount"], 2)
        self.assertEqual(summary["headMotion"]["settleLatency"]["p95Ms"], 295.0)
        self.assertEqual(summary["headMotion"]["settleLatency"]["incompleteCount"], 1)

    def test_active_transition_can_start_and_end_settle_latency(self):
        samples = [
            sample(
                0,
                16,
                0,
                targetTurn=0.5,
                currentTurn=0,
                bodyActive=False,
                bodySettled=False,
            ),
            sample(
                100,
                16,
                1,
                targetTurn=0.5,
                currentTurn=0.2,
                bodyActive=True,
                bodySettled=False,
            ),
            sample(
                300,
                16,
                0,
                targetTurn=0.5,
                currentTurn=0.5,
                bodyActive=False,
                bodySettled=False,
            ),
        ]

        latency = summarize_motion_samples(samples)["bodyMotion"]["settleLatency"]

        self.assertEqual(latency["sampleCount"], 1)
        self.assertEqual(latency["maxMs"], 200.0)
        self.assertEqual(latency["incompleteCount"], 0)

    def test_tracking_error_percentile_keeps_exact_zero_samples(self):
        samples = [
            sample(
                index * 16,
                16,
                0,
                targetTurn=1 if index == 4 else 0,
                currentTurn=0,
            )
            for index in range(5)
        ]

        tracking = summarize_motion_samples(samples)["bodyMotion"]["trackingError"]

        self.assertEqual(tracking["p95"], 0.8)
        self.assertEqual(tracking["max"], 1.0)

    def test_report_comparison_uses_same_environment_and_relative_regression(self):
        baseline = {
            "environment": {
                "browser": "chromium",
                "browserVersion": "126.0.6478.127",
                "viewport": "720x1280",
                "refreshRateBucketHz": 60,
            },
            "summary": {
                "frameIntervals": {"p95Ms": 20.0, "p99Ms": 30.0},
                "bodyMotion": {
                    "maxFrameStep": 0.8,
                    "skipCount": 0,
                    "trackingError": {"p95": 0.1, "max": 0.2},
                    "settleLatency": {"p95Ms": 600, "maxMs": 700},
                },
                "headMotion": {
                    "maxFrameStep": 0.7,
                    "skipCount": 0,
                    "trackingError": {"p95": 0.08, "max": 0.16},
                    "settleLatency": {"p95Ms": 500, "maxMs": 600},
                },
                "longTasks": {"count": 0},
            },
        }
        current = {
            "environment": {
                "browser": "chromium",
                "browserVersion": "126.0.6478.127",
                "viewport": "720x1280",
                "refreshRateBucketHz": 120,
            },
            "summary": {
                "frameIntervals": {"p95Ms": 25.0, "p99Ms": 38.0},
                "bodyMotion": {
                    "maxFrameStep": 1.1,
                    "skipCount": 3,
                    "trackingError": {"p95": 0.15, "max": 0.27},
                    "settleLatency": {"p95Ms": 850, "maxMs": 900},
                },
                "headMotion": {
                    "maxFrameStep": 0.8,
                    "skipCount": 0,
                    "trackingError": {"p95": 0.08, "max": 0.16},
                    "settleLatency": {"p95Ms": 500, "maxMs": 600},
                },
                "longTasks": {"count": 1},
            },
        }

        comparison = compare_motion_reports(current, baseline)

        self.assertTrue(comparison["compatible"])
        self.assertEqual(comparison["status"], "warn")
        self.assertIn("frame-p95-regression", comparison["reasons"])
        self.assertIn("body-frame-skip", comparison["reasons"])
        self.assertIn("body-tracking-error", comparison["reasons"])
        self.assertIn("body-settle-latency", comparison["reasons"])

        current["environment"]["viewport"] = "1440x1100"
        incompatible = compare_motion_reports(current, baseline)
        self.assertFalse(incompatible["compatible"])
        self.assertEqual(incompatible["status"], "incompatible")

        current["environment"]["viewport"] = "720x1280"
        current["environment"]["browserVersion"] = "126.0.6478.128"
        browser_update = compare_motion_reports(current, baseline)
        self.assertFalse(browser_update["compatible"])

        current["environment"]["browserVersion"] = "126.0.6478.127"
        current["summary"]["frameIntervals"]["p95Ms"] = 60.0
        current["summary"]["bodyMotion"]["maxFrameStep"] = 3.0
        current["summary"]["bodyMotion"]["trackingError"]["p95"] = 0.4
        current["summary"]["bodyMotion"]["settleLatency"]["p95Ms"] = 1300
        severe = compare_motion_reports(current, baseline)
        self.assertEqual(severe["status"], "fail")
        self.assertIn("body-tracking-error", severe["severeReasons"])
        self.assertIn("body-settle-latency", severe["severeReasons"])

    def test_quality_goals_separate_runtime_failure_from_motion_warning(self):
        report = {
            "runtime": {"consoleErrors": [], "pageErrors": []},
            "summary": {
                "frameCount": 500,
                "durationMs": 13000,
                "frameIntervals": {"p95Ms": 52, "p99Ms": 70},
                "bodyMotion": {
                    "maxFrameStep": 2.2,
                    "skipCount": 4,
                    "trackingError": {"p95": 0.3, "max": 0.7},
                    "settleLatency": {"p95Ms": 1500, "maxMs": 1900},
                },
                "headMotion": {
                    "maxFrameStep": 0.7,
                    "skipCount": 0,
                    "trackingError": {"p95": 0.1, "max": 0.2},
                    "settleLatency": {"p95Ms": 900, "maxMs": 1000},
                },
                "longTasks": {"count": 1},
            },
            "integrity": {"blackoutCount": 0},
        }
        result = evaluate_motion_report(report, expected_duration_ms=13000)
        self.assertEqual(result["status"], "warn")
        self.assertIn("frame-pacing", result["reasons"])
        self.assertIn("body-frame-skip", result["reasons"])
        self.assertIn("body-tracking-error", result["reasons"])
        self.assertIn("body-settle-latency", result["reasons"])
        self.assertEqual(result["goals"]["maxTrackingErrorP95"], 0.25)
        self.assertEqual(result["goals"]["maxTrackingError"], 0.65)
        self.assertEqual(result["goals"]["maxSettleLatencyP95Ms"], 1400.0)
        self.assertEqual(result["goals"]["maxSettleLatencyMs"], 1800.0)

        report["runtime"]["consoleErrors"] = ["webgl context lost"]
        failed = evaluate_motion_report(report, expected_duration_ms=13000)
        self.assertEqual(failed["status"], "fail")
        self.assertIn("browser-error", failed["reasons"])

    def test_repeat_aggregation_uses_median_and_mad(self):
        reports = []
        for p95, step, error, latency in (
            (18.0, 0.8, 0.1, 700),
            (20.0, 1.0, 0.2, 900),
            (30.0, 1.2, 0.3, 1300),
        ):
            reports.append(
                {
                    "environment": {"browser": "chrome", "viewport": "720x1280"},
                    "summary": {
                        "frameIntervals": {"p95Ms": p95, "p99Ms": p95 + 5},
                        "bodyMotion": {
                            "maxFrameStep": step,
                            "skipCount": 0,
                            "trackingError": {
                                "sampleCount": 100,
                                "p95": error,
                                "max": error + 0.1,
                            },
                            "settleLatency": {
                                "sampleCount": 3,
                                "p95Ms": latency,
                                "maxMs": latency + 100,
                                "incompleteCount": 0,
                            },
                        },
                        "headMotion": {
                            "maxFrameStep": 0.5,
                            "skipCount": 0,
                            "trackingError": {
                                "sampleCount": 100,
                                "p95": error / 2,
                                "max": error,
                            },
                            "settleLatency": {
                                "sampleCount": 3,
                                "p95Ms": latency - 100,
                                "maxMs": latency,
                                "incompleteCount": 0,
                            },
                        },
                        "longTasks": {"count": 0},
                    },
                }
            )

        aggregate = aggregate_motion_reports(reports)

        self.assertEqual(aggregate["repeatCount"], 3)
        self.assertEqual(aggregate["summary"]["frameIntervals"]["p95Ms"], 20.0)
        self.assertEqual(aggregate["variability"]["frameIntervals.p95Ms"]["mad"], 2.0)
        self.assertEqual(
            aggregate["summary"]["bodyMotion"]["trackingError"]["p95"],
            0.2,
        )
        self.assertEqual(
            aggregate["variability"]["bodyMotion.trackingError.p95"]["mad"],
            0.1,
        )
        self.assertEqual(
            aggregate["summary"]["bodyMotion"]["settleLatency"]["p95Ms"],
            900.0,
        )
        self.assertEqual(
            aggregate["summary"]["bodyMotion"]["trackingError"]["unit"],
            "turn",
        )
        self.assertEqual(
            aggregate["summary"]["bodyMotion"]["settleLatency"]["unit"],
            "ms",
        )

    def test_loop_requires_confirmation_before_observe_or_repair(self):
        self.assertEqual(
            decide_loop_action([{"status": "warn", "repairApplied": False}]),
            "confirm",
        )
        self.assertEqual(
            decide_loop_action([{"status": "fail", "repairApplied": False}]),
            "confirm",
        )
        self.assertEqual(
            decide_loop_action([{"status": "warn", "confirmation": True}]),
            "observe",
        )
        self.assertEqual(
            decide_loop_action([{"status": "fail", "confirmation": True}]),
            "repair",
        )

    def test_loop_honors_human_and_bounded_stop_rules(self):
        for status in ("invalid", "incompatible", "needs-human"):
            with self.subTest(status=status):
                self.assertEqual(decide_loop_action([{"status": status}]), "stop-human")
        self.assertEqual(
            decide_loop_action([{"status": "fail", "repairEligible": False}]),
            "stop-human",
        )
        self.assertEqual(
            decide_loop_action([{"status": "pass", "repairEligible": False}]),
            "observe",
        )
        self.assertEqual(
            decide_loop_action(
                [
                    {"status": "pass", "repairEligible": False},
                    {"status": "pass", "repairEligible": False},
                ]
            ),
            "stop-clean",
        )
        self.assertEqual(
            decide_loop_action(
                [
                    {"status": "fail", "repairApplied": True},
                    {"status": "fail", "repairApplied": True},
                    {"status": "fail", "repairApplied": True},
                ]
            ),
            "stop-max-repairs",
        )
        self.assertEqual(
            decide_loop_action([{"status": "pass"}, {"status": "pass"}]),
            "stop-clean",
        )
        self.assertEqual(
            decide_loop_action(
                [
                    {"status": "baseline", "isBaseline": True},
                    *[{"status": "warn"} for _ in range(6)],
                ],
                max_checks=6,
            ),
            "stop-max-checks",
        )
        self.assertEqual(
            decide_loop_action(
                [
                    {"status": "baseline", "isBaseline": True},
                    {"status": "warn"},
                ],
                max_checks=2,
            ),
            "confirm",
        )

    def test_loop_stops_after_two_non_improving_checks_following_repair(self):
        self.assertEqual(
            decide_loop_action(
                [{"status": "fail", "repairApplied": True}]
            ),
            "confirm",
        )
        self.assertEqual(
            decide_loop_action(
                [
                    {"status": "fail", "confirmation": True},
                    {"status": "fail", "repairApplied": True},
                    {"status": "warn", "confirmation": True},
                ]
            ),
            "stop-no-improvement",
        )
        self.assertEqual(
            decide_loop_action(
                [
                    {"status": "fail", "confirmation": True},
                    {"status": "fail", "repairApplied": True},
                    {"status": "pass", "confirmation": True},
                ]
            ),
            "observe",
        )


if __name__ == "__main__":
    unittest.main()
