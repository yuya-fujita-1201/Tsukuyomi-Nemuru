from contextlib import redirect_stderr
from io import StringIO
import json
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import TimeoutExpired
from unittest.mock import Mock, call, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_ai_motion_monitor import (  # noqa: E402
    MonitorAlreadyRunning,
    build_probe_command,
    exclusive_monitor_lock,
    parse_args,
    run_bounded_command,
    run_monitor,
    snapshot_expected_dirty_paths,
    terminate_process_group,
    unexpected_dirty_paths,
)


class MotionMonitorRunnerTests(unittest.TestCase):
    def test_dirty_guard_allows_monitor_outputs_but_blocks_source_edits(self):
        status = """ M output/perf/latest.json
 M output/perf/history.jsonl
?? output/perf/runs/next/
 M src/rig/puppet-engine.js
"""
        self.assertEqual(
            unexpected_dirty_paths(status),
            ["src/rig/puppet-engine.js"],
        )

    def test_dirty_guard_checks_both_old_and_new_rename_paths(self):
        status = """R  src/rig/old-engine.js -> output/perf/old-engine.js
R  output/perf/old-report.json -> src/rig/restored-report.json
"""

        self.assertEqual(
            unexpected_dirty_paths(status),
            ["src/rig/old-engine.js", "src/rig/restored-report.json"],
        )

    def test_dirty_guard_parses_nul_porcelain_renames_without_losing_source(self):
        status = (
            "R  output/perf/old-engine.js\0src/rig/old-engine.js\0"
            " M output/perf/latest.json\0"
        )

        self.assertEqual(
            unexpected_dirty_paths(status),
            ["src/rig/old-engine.js"],
        )

    def test_dirty_guard_allows_only_explicit_known_repair_paths(self):
        status = """ M src/rig/puppet-engine.js
 M test/layered-motion.test.js
 M docs/ai-motion-monitor.md
"""

        self.assertEqual(
            unexpected_dirty_paths(
                status,
                expected_dirty_paths=(
                    "src/rig/puppet-engine.js",
                    "test/layered-motion.test.js",
                ),
            ),
            ["docs/ai-motion-monitor.md"],
        )

    def test_probe_command_uses_three_repeats_for_baseline(self):
        command = build_probe_command(
            base_url="http://127.0.0.1:4174",
            baseline=Path("output/perf/baselines/current.json"),
            initialize=True,
            confirmation=False,
            repair_applied=False,
            policy={
                "measurement": {
                    "baselineRepeats": 3,
                    "monitorRepeats": 1,
                    "confirmationRepeats": 2,
                }
            },
        )
        self.assertIn("--write-baseline", command)
        self.assertEqual(command[command.index("--repeats") + 1], "3")

    def test_probe_command_compares_and_marks_repair(self):
        command = build_probe_command(
            base_url="http://127.0.0.1:4174",
            baseline=Path("output/perf/baselines/current.json"),
            initialize=False,
            confirmation=True,
            repair_applied=True,
            policy={
                "measurement": {
                    "baselineRepeats": 3,
                    "monitorRepeats": 1,
                    "confirmationRepeats": 2,
                }
            },
        )
        self.assertIn("--baseline", command)
        self.assertIn("--confirmation", command)
        self.assertIn("--repair-applied", command)
        self.assertEqual(command[command.index("--repeats") + 1], "2")

    def test_cli_uses_confirmation_name_and_rejects_old_confirm_name(self):
        args = parse_args(["--confirmation"])
        self.assertTrue(args.confirmation)

        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            parse_args(["--confirm"])

    @patch("scripts.run_ai_motion_monitor.os.killpg")
    def test_process_group_escalates_from_term_to_kill(self, killpg):
        process = Mock(pid=4321)
        process.wait.side_effect = [TimeoutExpired("preview", 1), 0]

        terminate_process_group(process, timeout=1)

        self.assertEqual(
            killpg.call_args_list,
            [call(4321, signal.SIGTERM), call(4321, signal.SIGKILL)],
        )

    @patch("scripts.run_ai_motion_monitor.terminate_process_group")
    @patch("scripts.run_ai_motion_monitor.subprocess.Popen")
    def test_bounded_command_kills_its_process_group_on_timeout(
        self, popen, terminate
    ):
        process = popen.return_value
        process.wait.side_effect = TimeoutExpired(["slow"], 7)

        with self.assertRaises(TimeoutExpired):
            run_bounded_command(["slow"], cwd=ROOT, timeout=7)

        popen.assert_called_once_with(
            ["slow"],
            cwd=ROOT,
            start_new_session=True,
        )
        terminate.assert_called_once_with(process)

    def test_monitor_lock_rejects_an_overlapping_run(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            lock_path = Path(temporary_directory) / "monitor.lock"
            with exclusive_monitor_lock(lock_path):
                with self.assertRaises(MonitorAlreadyRunning):
                    with exclusive_monitor_lock(lock_path):
                        self.fail("overlapping lock unexpectedly acquired")

    def test_expected_dirty_content_snapshot_detects_a_mid_run_edit(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "src/rig/puppet-engine.js"
            source.parent.mkdir(parents=True)
            source.write_text("before\n", encoding="utf-8")
            before = snapshot_expected_dirty_paths(
                ("src/rig/puppet-engine.js",), root=root
            )

            source.write_text("after\n", encoding="utf-8")

            self.assertNotEqual(
                snapshot_expected_dirty_paths(
                    ("src/rig/puppet-engine.js",), root=root
                ),
                before,
            )

    @patch("scripts.run_ai_motion_monitor.terminate_process_group")
    @patch("scripts.run_ai_motion_monitor.wait_for_server")
    @patch("scripts.run_ai_motion_monitor.subprocess.Popen")
    @patch("scripts.run_ai_motion_monitor.run_bounded_command")
    @patch("scripts.run_ai_motion_monitor.git_status")
    @patch("scripts.run_ai_motion_monitor.snapshot_expected_dirty_paths")
    def test_monitor_returns_nonzero_when_known_dirty_content_changes_during_probe(
        self,
        snapshot,
        git_status,
        run_command,
        popen,
        wait_for_server,
        terminate,
    ):
        del popen, wait_for_server, terminate
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            policy_path = root / "policy.json"
            policy_path.write_text(
                json.dumps(
                    {
                        "measurement": {
                            "baselineRepeats": 3,
                            "monitorRepeats": 1,
                            "confirmationRepeats": 2,
                        }
                    }
                ),
                encoding="utf-8",
            )
            args = parse_args(
                [
                    "--initialize-baseline",
                    "--repair-applied",
                    "--expected-dirty-path",
                    "src/rig/puppet-engine.js",
                    "--policy",
                    str(policy_path),
                    "--baseline",
                    str(root / "baseline.json"),
                ]
            )
            git_status.return_value = " M src/rig/puppet-engine.js\0"
            snapshot.side_effect = [
                {"src/rig/puppet-engine.js": "before"},
                {"src/rig/puppet-engine.js": "before"},
                {"src/rig/puppet-engine.js": "after"},
            ]
            run_command.side_effect = [
                subprocess.CompletedProcess(["npm", "run", "build"], 0),
                subprocess.CompletedProcess(["probe"], 0),
            ]

            with (
                patch("scripts.run_ai_motion_monitor.ROOT", root),
                redirect_stderr(StringIO()),
            ):
                result = run_monitor(args)

            self.assertNotEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
