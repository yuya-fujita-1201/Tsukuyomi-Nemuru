#!/usr/bin/env python3
"""Build, serve, and run the bounded AI motion monitor."""

from __future__ import annotations

import argparse
import errno
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "test/perf/motion-policy.v1.json"
DEFAULT_BASELINE = ROOT / "output/perf/baselines/current.json"
ALLOWED_DIRTY_PREFIXES = ("output/perf/",)
DEFAULT_BUILD_TIMEOUT_SECONDS = 300.0
DEFAULT_PROBE_TIMEOUT_SECONDS = 600.0
DIRTY_CHANGED_EXIT_CODE = 7
LOCK_KEY = hashlib.sha256(str(ROOT).encode("utf-8")).hexdigest()[:16]
DEFAULT_LOCK_PATH = (
    Path(tempfile.gettempdir()) / f"tsukuyomi-motion-monitor-{LOCK_KEY}.lock"
)


class MonitorAlreadyRunning(RuntimeError):
    """Raised when another monitor owns the checkout-wide execution lock."""


def _porcelain_paths(status: str) -> list[str]:
    """Extract every affected path, including both sides of renames/copies."""
    paths: list[str] = []
    if "\0" in status:
        records = status.split("\0")
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if not record:
                continue
            if len(record) < 4:
                continue
            state = record[:2]
            paths.append(record[3:])
            if "R" in state or "C" in state:
                if index < len(records) and records[index]:
                    paths.append(records[index])
                    index += 1
        return paths

    for line in status.splitlines():
        if not line.strip() or len(line) < 4:
            continue
        path_field = line[3:].strip()
        if " -> " in path_field:
            old_path, new_path = path_field.split(" -> ", 1)
            paths.extend((old_path, new_path))
        else:
            paths.append(path_field)
    return paths


def unexpected_dirty_paths(
    status: str,
    *,
    expected_dirty_paths: Sequence[str | Path] = (),
) -> list[str]:
    """Return worktree paths that are unsafe for an unattended monitor run."""
    expected = {str(path).replace(os.sep, "/") for path in expected_dirty_paths}
    unexpected: list[str] = []
    seen: set[str] = set()
    for path in _porcelain_paths(status):
        normalized = path.replace(os.sep, "/")
        if normalized in seen:
            continue
        seen.add(normalized)
        output_owned = normalized.startswith(ALLOWED_DIRTY_PREFIXES)
        if not output_owned and normalized not in expected:
            unexpected.append(normalized)
    return unexpected


def normalize_expected_dirty_paths(paths: Sequence[str | Path]) -> tuple[str, ...]:
    """Normalize an explicit repair allowlist to safe repo-relative paths."""
    normalized: list[str] = []
    for value in paths:
        path = Path(value)
        if path.is_absolute():
            try:
                path = path.resolve().relative_to(ROOT)
            except ValueError as error:
                raise ValueError(
                    f"expected dirty path is outside the repository: {value}"
                ) from error
        if not path.parts or path == Path(".") or ".." in path.parts:
            raise ValueError(f"invalid expected dirty path: {value}")
        repo_path = path.as_posix()
        if repo_path not in normalized:
            normalized.append(repo_path)
    return tuple(normalized)


def snapshot_expected_dirty_paths(
    paths: Sequence[str | Path], *, root: Path = ROOT
) -> dict[str, str]:
    """Hash the exact source content used by a repair verification run."""
    snapshot: dict[str, str] = {}
    for value in paths:
        repo_path = str(value).replace(os.sep, "/")
        source_path = root / repo_path
        digest = hashlib.sha256()
        if source_path.is_symlink():
            digest.update(b"symlink\0")
            digest.update(os.readlink(source_path).encode("utf-8"))
        elif source_path.is_file():
            digest.update(b"file\0")
            with source_path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        elif source_path.exists():
            raise ValueError(f"expected dirty path is not a file: {repo_path}")
        else:
            digest.update(b"missing\0")
        snapshot[repo_path] = digest.hexdigest()
    return snapshot


def changed_expected_dirty_paths(
    before: dict[str, str], *, root: Path = ROOT
) -> list[str]:
    """Return allowlisted repair files whose content changed mid-run."""
    after = snapshot_expected_dirty_paths(tuple(before), root=root)
    return [path for path, digest in before.items() if after.get(path) != digest]


@contextmanager
def exclusive_monitor_lock(path: Path) -> Iterator[None]:
    """Hold a non-blocking checkout lock for one complete monitor run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    acquired = False
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
            raise MonitorAlreadyRunning(
                f"another motion monitor owns {path}"
            ) from error
        acquired = True
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()}\n")
        handle.flush()
        yield
    finally:
        if acquired:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def terminate_process_group(
    process: subprocess.Popen[Any], *, timeout: float = 5.0
) -> None:
    """Terminate a subprocess and every descendant in its process group."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=timeout)


def run_bounded_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    check: bool = False,
) -> subprocess.CompletedProcess[Any]:
    """Run a command in an isolated process group with a hard deadline."""
    process = subprocess.Popen(list(command), cwd=cwd, start_new_session=True)
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        terminate_process_group(process)
        raise
    except BaseException:
        terminate_process_group(process)
        raise
    completed = subprocess.CompletedProcess(list(command), returncode)
    if check and returncode:
        raise subprocess.CalledProcessError(returncode, list(command))
    return completed


def build_probe_command(
    *,
    base_url: str,
    baseline: Path,
    initialize: bool,
    confirmation: bool,
    repair_applied: bool,
    policy: dict[str, Any],
    policy_path: Path = DEFAULT_POLICY,
) -> list[str]:
    measurement = policy["measurement"]
    if initialize:
        repeats = measurement["baselineRepeats"]
    elif confirmation:
        repeats = measurement["confirmationRepeats"]
    else:
        repeats = measurement["monitorRepeats"]
    command = [
        sys.executable,
        "test/e2e_ai_motion_perf.py",
        "--base-url",
        base_url,
        "--policy",
        str(policy_path),
        "--repeats",
        str(repeats),
        "--audio",
        "both",
    ]
    if initialize:
        command.extend(["--write-baseline", str(baseline)])
    else:
        command.extend(["--baseline", str(baseline)])
    if confirmation:
        command.append("--confirmation")
    if repair_applied:
        command.append("--repair-applied")
    return command


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the production-build AI motion monitor",
        allow_abbrev=False,
    )
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--port", type=int, default=4174)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--initialize-baseline", action="store_true")
    mode.add_argument("--confirmation", action="store_true")
    parser.add_argument("--force-baseline", action="store_true")
    parser.add_argument("--repair-applied", action="store_true")
    parser.add_argument(
        "--expected-dirty-path",
        action="append",
        default=[],
        type=Path,
        help="exact repo-relative repair path allowed to remain dirty; repeatable",
    )
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument(
        "--build-timeout-seconds",
        type=float,
        default=DEFAULT_BUILD_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--probe-timeout-seconds",
        type=float,
        default=DEFAULT_PROBE_TIMEOUT_SECONDS,
    )
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK_PATH)
    return parser.parse_args(argv)


def git_status() -> str:
    return subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout


def wait_for_server(url: str, process: subprocess.Popen, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"preview server exited with {process.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as error:  # noqa: BLE001 - retained for final diagnosis
            last_error = error
        time.sleep(0.2)
    raise TimeoutError(f"preview server did not become ready: {last_error}")


def run_monitor(args: argparse.Namespace) -> int:
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    baseline = args.baseline.resolve()
    if args.build_timeout_seconds <= 0 or args.probe_timeout_seconds <= 0:
        raise ValueError("build and probe timeouts must be positive")
    if args.initialize_baseline and baseline.exists() and not args.force_baseline:
        raise FileExistsError(
            f"baseline already exists: {baseline}; pass --force-baseline to replace it"
        )
    if not args.initialize_baseline and not baseline.exists():
        raise FileNotFoundError(
            f"baseline is missing: {baseline}; run --initialize-baseline first"
        )

    expected_dirty_paths = normalize_expected_dirty_paths(args.expected_dirty_path)
    if expected_dirty_paths and not args.repair_applied:
        print(
            "Expected dirty paths are accepted only with --repair-applied.",
            file=sys.stderr,
        )
        return 4
    dirty = unexpected_dirty_paths(
        git_status(), expected_dirty_paths=expected_dirty_paths
    )
    if dirty:
        print("Unexpected dirty worktree; motion monitor stopped:", file=sys.stderr)
        for path in dirty:
            print(f"- {path}", file=sys.stderr)
        return 4
    expected_dirty_snapshot = snapshot_expected_dirty_paths(
        expected_dirty_paths, root=ROOT
    )

    def stop_if_expected_dirty_changed() -> bool:
        changed = changed_expected_dirty_paths(expected_dirty_snapshot, root=ROOT)
        if not changed:
            return False
        print(
            "Known repair files changed while the motion monitor was running; "
            "the measurement is invalid and must not be used:",
            file=sys.stderr,
        )
        for path in changed:
            print(f"- {path}", file=sys.stderr)
        return True

    if not args.skip_build:
        run_bounded_command(
            ["npm", "run", "build"],
            cwd=ROOT,
            timeout=args.build_timeout_seconds,
            check=True,
        )
        if stop_if_expected_dirty_changed():
            return DIRTY_CHANGED_EXIT_CODE

    output_root = ROOT / "output/perf"
    output_root.mkdir(parents=True, exist_ok=True)
    log_path = output_root / "preview.log"
    base_url = f"http://127.0.0.1:{args.port}"
    with log_path.open("w", encoding="utf-8") as log:
        server = subprocess.Popen(
            [
                "npm",
                "run",
                "preview",
                "--",
                "--port",
                str(args.port),
                "--strictPort",
            ],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            wait_for_server(f"{base_url}/?variant=parameter", server)
            command = build_probe_command(
                base_url=base_url,
                baseline=baseline,
                initialize=args.initialize_baseline,
                confirmation=args.confirmation,
                repair_applied=args.repair_applied,
                policy=policy,
                policy_path=args.policy.resolve(),
            )
            result = run_bounded_command(
                command,
                cwd=ROOT,
                timeout=args.probe_timeout_seconds,
            )
            if stop_if_expected_dirty_changed():
                return DIRTY_CHANGED_EXIT_CODE
            return result.returncode
        finally:
            terminate_process_group(server)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        with exclusive_monitor_lock(args.lock_file.resolve()):
            return run_monitor(args)
    except MonitorAlreadyRunning as error:
        print(f"Motion monitor stopped: {error}", file=sys.stderr)
        return 5
    except subprocess.TimeoutExpired as error:
        print(
            f"Motion monitor stopped after command timeout: {error}",
            file=sys.stderr,
        )
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
