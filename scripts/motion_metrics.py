"""Pure helpers for repeatable real-time motion monitoring.

The browser probe deliberately emits raw samples.  Keeping aggregation and
comparison here makes the 30-minute loop deterministic and unit-testable.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Iterable


def _finite_positive(values: Iterable[Any]) -> list[float]:
    cleaned = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number) and number > 0:
            cleaned.append(number)
    return cleaned


def percentile(values: Iterable[Any], rank: float) -> float | None:
    """Return a linearly interpolated percentile for finite positive values."""
    cleaned = sorted(_finite_positive(values))
    if not cleaned:
        return None
    bounded_rank = min(100.0, max(0.0, float(rank)))
    position = (len(cleaned) - 1) * bounded_rank / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return cleaned[lower]
    fraction = position - lower
    return cleaned[lower] + (cleaned[upper] - cleaned[lower]) * fraction


def _nonnegative_percentile(values: Iterable[Any], rank: float) -> float | None:
    cleaned = []
    for value in values:
        number = _finite_number(value)
        if number is not None and number >= 0:
            cleaned.append(number)
    cleaned.sort()
    if not cleaned:
        return None
    bounded_rank = min(100.0, max(0.0, float(rank)))
    position = (len(cleaned) - 1) * bounded_rank / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return cleaned[lower]
    fraction = position - lower
    return cleaned[lower] + (cleaned[upper] - cleaned[lower]) * fraction


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def summarize_frame_intervals(intervals: Iterable[Any]) -> dict[str, Any]:
    """Summarize raw rAF or ticker intervals in milliseconds."""
    intervals = _finite_positive(intervals)
    mean = sum(intervals) / len(intervals) if intervals else None
    return {
        "count": len(intervals),
        "meanMs": _rounded(mean),
        "p50Ms": _rounded(percentile(intervals, 50)),
        "p95Ms": _rounded(percentile(intervals, 95)),
        "p99Ms": _rounded(percentile(intervals, 99)),
        "maxMs": _rounded(max(intervals) if intervals else None),
        "over33MsCount": sum(value > 33.0 for value in intervals),
        "over50MsCount": sum(value > 50.0 for value in intervals),
        "effectiveFps": _rounded(1000.0 / mean) if mean else None,
    }


def _frame_interval_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    return summarize_frame_intervals(
        sample.get("frameIntervalMs") for sample in samples
    )


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _settle_latency_summary(
    samples: list[dict[str, Any]],
    *,
    target_key: str,
    active_key: str,
    settled_key: str,
) -> dict[str, Any]:
    """Measure target/active transition start until settled or atlas exit.

    Latencies are milliseconds. A target transition that has not completed by
    the last sample is reported separately instead of being converted into an
    artificially short latency.
    """
    latencies: list[float] = []
    pending_started_at: float | None = None
    pending_saw_active = False
    previous_target: float | None = None
    previous_cue: Any = None
    previous_active = False
    have_previous = False

    for sample in samples:
        at_ms = _finite_number(sample.get("atMs"))
        target = _finite_number(sample.get(target_key))
        active_known = active_key in sample
        active = bool(sample.get(active_key)) if active_known else False
        settled = sample.get(settled_key) is True
        cue = sample.get("cueIndex")

        target_changed = (
            have_previous
            and target is not None
            and previous_target is not None
            and abs(target - previous_target) > 0.0005
        )
        cue_changed = have_previous and cue != previous_cue
        active_started = active_known and active and (
            not have_previous or not previous_active
        )
        triggered = target_changed or cue_changed or active_started

        if pending_started_at is None and triggered and at_ms is not None:
            pending_started_at = at_ms
            pending_saw_active = active

        if pending_started_at is not None:
            pending_saw_active = pending_saw_active or active
            exited_active_atlas = active_known and pending_saw_active and not active
            if (settled or exited_active_atlas) and at_ms is not None:
                latencies.append(max(0.0, at_ms - pending_started_at))
                pending_started_at = None
                pending_saw_active = False

        if target is not None:
            previous_target = target
        previous_cue = cue
        previous_active = active
        have_previous = True

    return {
        "unit": "ms",
        "sampleCount": len(latencies),
        "p95Ms": _rounded(_nonnegative_percentile(latencies, 95)) or 0.0,
        "maxMs": _rounded(max(latencies) if latencies else 0.0),
        "incompleteCount": int(pending_started_at is not None),
    }


def _motion_axis_summary(
    samples: list[dict[str, Any]],
    *,
    position_key: str,
    current_key: str,
    target_key: str,
    active_key: str,
    direction_key: str,
    settled_key: str,
) -> dict[str, Any]:
    positions: list[float] = []
    for sample in samples:
        number = _finite_number(sample.get(position_key))
        if number is not None:
            positions.append(number)

    has_atlas_metadata = any(
        active_key in sample or direction_key in sample for sample in samples
    )
    if has_atlas_metadata:
        steps = []
        for previous, current in zip(samples, samples[1:]):
            previous_position = _finite_number(previous.get(position_key))
            current_position = _finite_number(current.get(position_key))
            previous_direction = _finite_number(previous.get(direction_key))
            current_direction = _finite_number(current.get(direction_key))
            if (
                previous_position is None
                or current_position is None
                or not bool(previous.get(active_key))
                or not bool(current.get(active_key))
                or previous_direction is None
                or current_direction is None
                or previous_direction == 0
                or previous_direction != current_direction
            ):
                continue
            steps.append(abs(current_position - previous_position))
    else:
        # Backwards-compatible fallback for older probes without transition
        # metadata. It intentionally retains the original position-only logic.
        steps = [
            abs(current - previous)
            for previous, current in zip(positions, positions[1:])
        ]

    tracking_errors = []
    for sample in samples:
        current = _finite_number(sample.get(current_key))
        target = _finite_number(sample.get(target_key))
        if current is not None and target is not None:
            tracking_errors.append(abs(target - current))

    return {
        "sampleCount": len(positions),
        "maxFrameStep": _rounded(max(steps) if steps else 0.0),
        "p95FrameStep": _rounded(percentile(steps, 95)) or 0.0,
        "skipCount": sum(step > 1.0 for step in steps),
        "trackingError": {
            # Normalized turn units: 0 is exact and 2 is the full -1 to +1 span.
            "unit": "turn",
            "sampleCount": len(tracking_errors),
            "p95": _rounded(_nonnegative_percentile(tracking_errors, 95)) or 0.0,
            "max": _rounded(max(tracking_errors) if tracking_errors else 0.0),
        },
        "settleLatency": _settle_latency_summary(
            samples,
            target_key=target_key,
            active_key=active_key,
            settled_key=settled_key,
        ),
    }


def summarize_motion_samples(
    samples: list[dict[str, Any]],
    *,
    long_tasks: Iterable[Any] = (),
) -> dict[str, Any]:
    """Aggregate browser samples without applying environment policy."""
    task_durations = _finite_positive(
        task.get("duration", 0) if isinstance(task, dict) else task
        for task in long_tasks
    )
    cue_transitions = sum(
        current.get("cueIndex") != previous.get("cueIndex")
        for previous, current in zip(samples, samples[1:])
    )
    blink_values = [
        float(sample.get("blink", 0) or 0)
        for sample in samples
        if math.isfinite(float(sample.get("blink", 0) or 0))
    ]
    return {
        "frameCount": len(samples),
        "durationMs": _rounded(
            (float(samples[-1]["atMs"]) - float(samples[0]["atMs"]))
            if len(samples) >= 2
            else 0.0
        ),
        "frameIntervals": _frame_interval_summary(samples),
        "bodyMotion": _motion_axis_summary(
            samples,
            position_key="bodyFramePosition",
            current_key="currentTurn",
            target_key="targetTurn",
            active_key="bodyActive",
            direction_key="bodyDirection",
            settled_key="bodySettled",
        ),
        "headMotion": _motion_axis_summary(
            samples,
            position_key="headFramePosition",
            current_key="currentHeadTurn",
            target_key="targetHeadTurn",
            active_key="headActive",
            direction_key="headDirection",
            settled_key="headSettled",
        ),
        "longTasks": {
            "count": len(task_durations),
            "totalMs": _rounded(sum(task_durations)),
            "maxMs": _rounded(max(task_durations) if task_durations else 0.0),
        },
        "cueTransitions": cue_transitions,
        "blink": {
            "sampleCount": sum(value > 0.02 for value in blink_values),
            "max": _rounded(max(blink_values) if blink_values else 0.0),
        },
    }


def _environment_signature(report: dict[str, Any]) -> dict[str, Any]:
    environment = report.get("environment") or {}
    keys = (
        "browser",
        "browserMajor",
        "browserVersion",
        "viewport",
        "deviceScaleFactor",
        "headless",
        "audio",
        "platform",
        "webglRenderer",
    )
    return {key: environment.get(key) for key in keys if key in environment}


def _optional_metric(report: dict[str, Any], *path: str) -> float | None:
    value: Any = report.get("summary", {})
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return _finite_number(value)


def _metric(report: dict[str, Any], *path: str, default: float = 0.0) -> float:
    value = _optional_metric(report, *path)
    return default if value is None else value


def _mad(report: dict[str, Any], *path: str) -> float:
    key = ".".join(path)
    try:
        value = float((report.get("variability") or {})[key]["mad"])
    except (KeyError, TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) and value >= 0 else 0.0


def _relative_regression_level(
    current: dict[str, Any],
    baseline: dict[str, Any],
    path: tuple[str, ...],
    *,
    warn_factor: float,
    warn_delta: float,
    fail_factor: float,
    fail_delta: float,
) -> str | None:
    """Return warn/fail only when both reports contain the metric."""
    current_value = _optional_metric(current, *path)
    baseline_value = _optional_metric(baseline, *path)
    if current_value is None or baseline_value is None:
        return None
    variability = _mad(baseline, *path)
    fail_threshold = max(
        baseline_value * fail_factor,
        baseline_value + fail_delta,
        baseline_value + 5.0 * variability,
    )
    if current_value > fail_threshold:
        return "fail"
    warn_threshold = max(
        baseline_value * warn_factor,
        baseline_value + warn_delta,
        baseline_value + 3.0 * variability,
    )
    return "warn" if current_value > warn_threshold else None


def compare_motion_reports(
    current: dict[str, Any], baseline: dict[str, Any]
) -> dict[str, Any]:
    """Compare like-for-like runs and identify material relative regressions."""
    current_environment = _environment_signature(current)
    baseline_environment = _environment_signature(baseline)
    if current_environment != baseline_environment:
        return {
            "compatible": False,
            "status": "incompatible",
            "reasons": ["environment-mismatch"],
            "currentEnvironment": current_environment,
            "baselineEnvironment": baseline_environment,
        }

    reasons: list[str] = []
    severe_reasons: list[str] = []
    current_p95 = _metric(current, "frameIntervals", "p95Ms")
    baseline_p95 = _metric(baseline, "frameIntervals", "p95Ms")
    baseline_p95_mad = _mad(baseline, "frameIntervals", "p95Ms")
    if baseline_p95 > 0 and current_p95 > max(
        baseline_p95 * 1.2,
        baseline_p95 + 2.0,
        baseline_p95 + 3.0 * baseline_p95_mad,
    ):
        reasons.append("frame-p95-regression")
        if current_p95 > max(
            baseline_p95 * 1.4,
            baseline_p95 + 5.0,
            baseline_p95 + 5.0 * baseline_p95_mad,
        ):
            severe_reasons.append("frame-p95-regression")

    current_p99 = _metric(current, "frameIntervals", "p99Ms")
    baseline_p99 = _metric(baseline, "frameIntervals", "p99Ms")
    baseline_p99_mad = _mad(baseline, "frameIntervals", "p99Ms")
    if baseline_p99 > 0 and current_p99 > max(
        baseline_p99 * 1.25,
        baseline_p99 + 3.0,
        baseline_p99 + 3.0 * baseline_p99_mad,
    ):
        reasons.append("frame-p99-regression")
        if current_p99 > max(
            baseline_p99 * 1.5,
            baseline_p99 + 8.0,
            baseline_p99 + 5.0 * baseline_p99_mad,
        ):
            severe_reasons.append("frame-p99-regression")

    for axis, label in (("bodyMotion", "body"), ("headMotion", "head")):
        current_step = _metric(current, axis, "maxFrameStep")
        baseline_step = _metric(baseline, axis, "maxFrameStep")
        baseline_step_mad = _mad(baseline, axis, "maxFrameStep")
        current_skips = _metric(current, axis, "skipCount")
        baseline_skips = _metric(baseline, axis, "skipCount")
        if current_step > max(
            1.0,
            baseline_step * 1.25,
            baseline_step + 3.0 * baseline_step_mad,
        ) or (
            current_skips > baseline_skips + 1
        ):
            reason = f"{label}-frame-skip"
            reasons.append(reason)
            if current_step > max(
                1.5,
                baseline_step * 1.6,
                baseline_step + 5.0 * baseline_step_mad,
            ) or (
                current_skips > baseline_skips + 5
            ):
                severe_reasons.append(reason)

        tracking_levels = (
            _relative_regression_level(
                current,
                baseline,
                (axis, "trackingError", "p95"),
                warn_factor=1.25,
                warn_delta=0.025,
                fail_factor=1.6,
                fail_delta=0.075,
            ),
            _relative_regression_level(
                current,
                baseline,
                (axis, "trackingError", "max"),
                warn_factor=1.25,
                warn_delta=0.05,
                fail_factor=1.6,
                fail_delta=0.15,
            ),
        )
        if any(level in {"warn", "fail"} for level in tracking_levels):
            reason = f"{label}-tracking-error"
            reasons.append(reason)
            if "fail" in tracking_levels:
                severe_reasons.append(reason)

        settle_levels = (
            _relative_regression_level(
                current,
                baseline,
                (axis, "settleLatency", "p95Ms"),
                warn_factor=1.25,
                warn_delta=120.0,
                fail_factor=1.6,
                fail_delta=350.0,
            ),
            _relative_regression_level(
                current,
                baseline,
                (axis, "settleLatency", "maxMs"),
                warn_factor=1.25,
                warn_delta=150.0,
                fail_factor=1.6,
                fail_delta=450.0,
            ),
        )
        if any(level in {"warn", "fail"} for level in settle_levels):
            reason = f"{label}-settle-latency"
            reasons.append(reason)
            if "fail" in settle_levels:
                severe_reasons.append(reason)

    if _metric(current, "longTasks", "count") > (
        _metric(baseline, "longTasks", "count") + 1
    ):
        reasons.append("long-task-regression")
        if _metric(current, "longTasks", "count") > (
            _metric(baseline, "longTasks", "count") + 3
        ):
            severe_reasons.append("long-task-regression")

    return {
        "compatible": True,
        "status": "fail" if severe_reasons else ("warn" if reasons else "pass"),
        "reasons": reasons,
        "severeReasons": severe_reasons,
    }


def evaluate_motion_report(
    report: dict[str, Any],
    *,
    expected_duration_ms: float,
    goals: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Apply broad quality goals without pretending they are a device baseline."""
    policy = {
        "minimumDurationRatio": 0.85,
        "minimumFrames": 60,
        "p95FrameIntervalMs": 40.0,
        "p99FrameIntervalMs": 60.0,
        "maxAtlasFrameStep": 1.25,
        # Tracking error is in normalized turn units (-1 through +1).
        "maxTrackingErrorP95": 0.25,
        "maxTrackingError": 0.65,
        # Settle latency goals are milliseconds from transition start.
        "maxSettleLatencyP95Ms": 1400.0,
        "maxSettleLatencyMs": 1800.0,
        "maxLongTasks": 0,
    }
    policy.update(goals or {})

    fatal: list[str] = []
    warnings: list[str] = []
    runtime = report.get("runtime") or {}
    if runtime.get("consoleErrors") or runtime.get("pageErrors"):
        fatal.append("browser-error")
    if _metric(report, "frameCount") < policy["minimumFrames"]:
        fatal.append("insufficient-frame-samples")
    if _metric(report, "durationMs") < (
        float(expected_duration_ms) * policy["minimumDurationRatio"]
    ):
        fatal.append("short-capture")
    if float((report.get("integrity") or {}).get("blackoutCount", 0) or 0) > 0:
        fatal.append("layer-blackout")

    if (
        _metric(report, "frameIntervals", "p95Ms")
        > policy["p95FrameIntervalMs"]
        or _metric(report, "frameIntervals", "p99Ms")
        > policy["p99FrameIntervalMs"]
    ):
        warnings.append("frame-pacing")
    for axis, label in (("bodyMotion", "body"), ("headMotion", "head")):
        if (
            _metric(report, axis, "maxFrameStep")
            > policy["maxAtlasFrameStep"]
        ):
            warnings.append(f"{label}-frame-skip")
        if (
            _metric(report, axis, "trackingError", "p95")
            > policy["maxTrackingErrorP95"]
            or _metric(report, axis, "trackingError", "max")
            > policy["maxTrackingError"]
        ):
            warnings.append(f"{label}-tracking-error")
        if (
            _metric(report, axis, "settleLatency", "p95Ms")
            > policy["maxSettleLatencyP95Ms"]
            or _metric(report, axis, "settleLatency", "maxMs")
            > policy["maxSettleLatencyMs"]
        ):
            warnings.append(f"{label}-settle-latency")
    if _metric(report, "longTasks", "count") > policy["maxLongTasks"]:
        warnings.append("long-task")

    reasons = fatal + warnings
    return {
        "status": "fail" if fatal else ("warn" if warnings else "pass"),
        "reasons": reasons,
        "fatalReasons": fatal,
        "warningReasons": warnings,
        "repairEligible": not fatal and bool(warnings),
        "goals": policy,
    }


_AGGREGATE_PATHS = (
    ("frameCount",),
    ("durationMs",),
    ("frameIntervals", "meanMs"),
    ("frameIntervals", "p50Ms"),
    ("frameIntervals", "p95Ms"),
    ("frameIntervals", "p99Ms"),
    ("frameIntervals", "maxMs"),
    ("frameIntervals", "over33MsCount"),
    ("frameIntervals", "over50MsCount"),
    ("frameIntervals", "effectiveFps"),
    ("bodyMotion", "maxFrameStep"),
    ("bodyMotion", "p95FrameStep"),
    ("bodyMotion", "skipCount"),
    ("bodyMotion", "trackingError", "sampleCount"),
    ("bodyMotion", "trackingError", "p95"),
    ("bodyMotion", "trackingError", "max"),
    ("bodyMotion", "settleLatency", "sampleCount"),
    ("bodyMotion", "settleLatency", "p95Ms"),
    ("bodyMotion", "settleLatency", "maxMs"),
    ("bodyMotion", "settleLatency", "incompleteCount"),
    ("headMotion", "maxFrameStep"),
    ("headMotion", "p95FrameStep"),
    ("headMotion", "skipCount"),
    ("headMotion", "trackingError", "sampleCount"),
    ("headMotion", "trackingError", "p95"),
    ("headMotion", "trackingError", "max"),
    ("headMotion", "settleLatency", "sampleCount"),
    ("headMotion", "settleLatency", "p95Ms"),
    ("headMotion", "settleLatency", "maxMs"),
    ("headMotion", "settleLatency", "incompleteCount"),
    ("longTasks", "count"),
    ("longTasks", "totalMs"),
    ("longTasks", "maxMs"),
    ("cueTransitions",),
    ("blink", "sampleCount"),
    ("blink", "max"),
)


def _nested_value(report: dict[str, Any], path: tuple[str, ...]) -> float | None:
    value: Any = report.get("summary", {})
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _set_nested(target: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    current = target
    for key in path[:-1]:
        current = current.setdefault(key, {})
    current[path[-1]] = value


def aggregate_motion_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Collapse repeated like-for-like runs to median values plus MAD."""
    if not reports:
        raise ValueError("at least one motion report is required")
    signature = _environment_signature(reports[0])
    if any(_environment_signature(report) != signature for report in reports[1:]):
        raise ValueError("motion report environments do not match")

    summary: dict[str, Any] = {}
    variability: dict[str, Any] = {}
    for path in _AGGREGATE_PATHS:
        values = [
            value
            for report in reports
            if (value := _nested_value(report, path)) is not None
        ]
        if not values:
            continue
        median = float(statistics.median(values))
        mad = float(statistics.median(abs(value - median) for value in values))
        _set_nested(summary, path, _rounded(median))
        variability[".".join(path)] = {
            "median": _rounded(median),
            "mad": _rounded(mad),
            "min": _rounded(min(values)),
            "max": _rounded(max(values)),
        }

    for axis in ("bodyMotion", "headMotion"):
        summary.setdefault(axis, {}).setdefault("trackingError", {})["unit"] = "turn"
        summary.setdefault(axis, {}).setdefault("settleLatency", {})["unit"] = "ms"

    console_errors = [
        error
        for report in reports
        for error in (report.get("runtime") or {}).get("consoleErrors", [])
    ]
    page_errors = [
        error
        for report in reports
        for error in (report.get("runtime") or {}).get("pageErrors", [])
    ]
    blackout_count = sum(
        int((report.get("integrity") or {}).get("blackoutCount", 0) or 0)
        for report in reports
    )
    return {
        "environment": reports[0].get("environment", {}),
        "repeatCount": len(reports),
        "summary": summary,
        "variability": variability,
        "runtime": {
            "consoleErrors": console_errors,
            "pageErrors": page_errors,
        },
        "integrity": {"blackoutCount": blackout_count},
    }


def decide_loop_action(
    history: list[dict[str, Any]],
    *,
    max_repairs: int = 3,
    clean_runs_to_stop: int = 2,
    max_checks: int | None = None,
) -> str:
    """Return the next safe action for one already-filtered campaign history."""
    checks = [entry for entry in history if not bool(entry.get("isBaseline"))]
    if not checks:
        return "observe"
    latest = checks[-1]
    if latest.get("status") in {"invalid", "needs-human", "incompatible"}:
        return "stop-human"
    if (
        latest.get("status") in {"warn", "fail"}
        and latest.get("repairEligible") is False
    ):
        return "stop-human"
    if max_checks is not None and len(checks) >= max_checks:
        return "stop-max-checks"
    if sum(bool(entry.get("repairApplied")) for entry in checks) >= max_repairs:
        return "stop-max-repairs"
    if len(checks) >= clean_runs_to_stop and all(
        entry.get("status") == "pass"
        for entry in checks[-clean_runs_to_stop:]
    ):
        return "stop-clean"

    repair_indexes = [
        index for index, entry in enumerate(checks) if entry.get("repairApplied")
    ]
    if repair_indexes:
        after_latest_repair = checks[repair_indexes[-1] :]
        if len(after_latest_repair) >= 2 and all(
            entry.get("status") in {"warn", "fail"}
            for entry in after_latest_repair[:2]
        ):
            return "stop-no-improvement"

    status = latest.get("status")
    if status in {"warn", "fail"} and not bool(
        latest.get("confirmation") or latest.get("isConfirmation")
    ):
        return "confirm"
    if status == "fail":
        return "repair"
    return "observe"
