#!/usr/bin/env python3
"""Measure the AI performance in wall-clock time with system Chrome.

Unlike the deterministic visual E2E tests, this probe leaves Pixi's ticker
running.  It records rAF cadence, ticker cost, atlas movement, long tasks, and
runtime integrity without taking screenshots during the measured interval.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.motion_metrics import (  # noqa: E402
    aggregate_motion_reports,
    compare_motion_reports,
    decide_loop_action,
    evaluate_motion_report,
    summarize_frame_intervals,
    summarize_motion_samples,
)


DEFAULT_POLICY = ROOT / "test/perf/motion-policy.v1.json"
DEFAULT_OUTPUT_ROOT = ROOT / "output/perf"
AUDIO_FIXTURE = ROOT / "output/audio/tsukuyomi-rms-demo.wav"


PROBE_INIT_SCRIPT = r"""
(() => {
  const probe = {
    active: false,
    startedAt: 0,
    lastRaf: null,
    raf: [],
    samples: [],
    ticks: [],
    longTasks: [],
    longFrames: [],
    blackoutCount: 0,
    invalidStateCount: 0,
    engineInstalled: false,
    heapStart: null,
    heapEnd: null,
  };
  window.__MOTION_PROBE__ = probe;

  const rafLoop = (timestamp) => {
    if (probe.active) {
      if (probe.lastRaf !== null) {
        probe.raf.push({
          atMs: timestamp - probe.startedAt,
          deltaMs: timestamp - probe.lastRaf,
        });
      }
      probe.lastRaf = timestamp;
    } else {
      probe.lastRaf = null;
    }
    requestAnimationFrame(rafLoop);
  };
  requestAnimationFrame(rafLoop);

  for (const type of ["longtask", "long-animation-frame"]) {
    if (!PerformanceObserver.supportedEntryTypes.includes(type)) continue;
    new PerformanceObserver((list) => {
      if (!probe.active) return;
      const target = type === "longtask" ? probe.longTasks : probe.longFrames;
      for (const entry of list.getEntries()) {
        target.push({
          atMs: entry.startTime - probe.startedAt,
          duration: entry.duration,
          blockingDuration: entry.blockingDuration ?? null,
        });
      }
    }).observe({ type, buffered: true });
  }
})();
"""


INSTALL_ENGINE_PROBE = r"""
() => {
  const engine = window.__PUPPET__;
  const probe = window.__MOTION_PROBE__;
  if (!engine || !probe) throw new Error("motion probe booted before engine");
  if (probe.engineInstalled) return probe.metadata;

  const signedPosition = (active, blend) => {
    if (!active || !blend) return 0;
    const direction = blend.direction < 0 ? -1 : 1;
    return direction * (blend.lowerIndex + blend.upperAlpha);
  };
  const motionGroups = [
    ...Object.values(engine.headTurnGroups || {}),
    ...Object.values(engine.bodyTurnGroups || {}),
  ];
  const visibleAlpha = () => {
    let total = Number(engine.frontGroup?.alpha) || 0;
    for (const group of motionGroups) {
      if (group?.visible) total += Number(group.alpha) || 0;
    }
    return total;
  };

  const previousOnUpdate = engine.onUpdate;
  let lastStateAt = null;
  engine.onUpdate = (state) => {
    const now = performance.now();
    if (probe.active) {
      const bodyFramePosition = signedPosition(
        state.bodyTurnSequenceActive,
        state.bodyTurnFrameBlend,
      );
      const headFramePosition = signedPosition(
        state.headTurnSequenceActive,
        state.headTurnFrameBlend,
      );
      const finiteValues = [
        bodyFramePosition,
        headFramePosition,
        state.elapsed,
        state.pose?.turn,
        state.pose?.headTurn,
        engine.currentTurn,
        engine.currentHeadTurn,
      ];
      if (!finiteValues.every(Number.isFinite)) probe.invalidStateCount += 1;
      if (visibleAlpha() <= 0.01) probe.blackoutCount += 1;
      probe.samples.push({
        atMs: now - probe.startedAt,
        frameIntervalMs: lastStateAt === null ? null : now - lastStateAt,
        scriptElapsed: state.elapsed,
        cueIndex: state.cueIndex,
        audioLevel: state.audioLevel,
        blink: state.pose?.blink ?? 0,
        turn: state.pose?.turn ?? 0,
        headTurn: state.pose?.headTurn ?? 0,
        targetTurn: engine.targetPose?.turn ?? 0,
        targetHeadTurn: engine.targetPose?.headTurn ?? 0,
        currentTurn: engine.currentTurn,
        currentHeadTurn: engine.currentHeadTurn,
        bodyFramePosition,
        bodyActive: state.bodyTurnSequenceActive,
        bodySettled: state.bodyTurnSettled,
        bodyDirection: state.bodyTurnFrameBlend?.direction ?? 0,
        headFramePosition,
        headActive: state.headTurnSequenceActive,
        headSettled: state.headTurnSettled,
        headDirection: state.headTurnFrameBlend?.direction ?? 0,
        sideMotionLocked: state.sideMotionLocked,
      });
      lastStateAt = now;
    }
    return previousOnUpdate?.(state);
  };

  const originalTick = engine.tick;
  engine.tick = function measuredTick(deltaSeconds) {
    const startedAt = performance.now();
    try {
      return originalTick.call(this, deltaSeconds);
    } finally {
      if (probe.active) {
        probe.ticks.push({
          atMs: startedAt - probe.startedAt,
          deltaMs: deltaSeconds * 1000,
          cpuMs: performance.now() - startedAt,
        });
      }
    }
  };

  const sources = [
    ...new Set(Object.values(engine.textures).map((texture) => texture.source)),
  ];
  const textureRgbaBytes = sources.reduce((total, source) => {
    const width = Number(source?.width ?? source?.pixelWidth ?? 0) || 0;
    const height = Number(source?.height ?? source?.pixelHeight ?? 0) || 0;
    return total + width * height * 4;
  }, 0);
  const canvas = engine.app.canvas;
  const gl = engine.app.renderer?.gl
    ?? canvas.getContext("webgl2")
    ?? canvas.getContext("webgl");
  const debugInfo = gl?.getExtension("WEBGL_debug_renderer_info");
  const webglVendor = debugInfo
    ? gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL)
    : gl?.getParameter(gl.VENDOR) ?? "unknown";
  const webglRenderer = debugInfo
    ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL)
    : gl?.getParameter(gl.RENDERER) ?? "unknown";

  probe.start = () => {
    probe.raf = [];
    probe.samples = [];
    probe.ticks = [];
    probe.longTasks = [];
    probe.longFrames = [];
    probe.blackoutCount = 0;
    probe.invalidStateCount = 0;
    probe.lastRaf = null;
    lastStateAt = null;
    probe.startedAt = performance.now();
    probe.heapStart = performance.memory?.usedJSHeapSize ?? null;
    probe.active = true;
  };
  probe.stop = () => {
    probe.active = false;
    probe.heapEnd = performance.memory?.usedJSHeapSize ?? null;
    return {
      raf: probe.raf,
      samples: probe.samples,
      ticks: probe.ticks,
      longTasks: probe.longTasks,
      longFrames: probe.longFrames,
      blackoutCount: probe.blackoutCount,
      invalidStateCount: probe.invalidStateCount,
      heapStart: probe.heapStart,
      heapEnd: probe.heapEnd,
    };
  };
  probe.metadata = {
    readyAtMs: performance.now(),
    visibilityState: document.visibilityState,
    hasFocus: document.hasFocus(),
    textureSourceCount: sources.length,
    textureRgbaBytes,
    pixiResolution: engine.app.renderer.resolution,
    rendererWidth: engine.app.screen.width,
    rendererHeight: engine.app.screen.height,
    webglVendor,
    webglRenderer,
    maxTextureSize: gl?.getParameter(gl.MAX_TEXTURE_SIZE) ?? null,
    bundleNames: performance.getEntriesByType("resource")
      .map((entry) => entry.name.split("/").pop())
      .filter((name) => /^index-.*\.js$/.test(name)),
  };
  probe.engineInstalled = true;
  return probe.metadata;
}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure wall-clock AI motion in system Chrome"
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("BASE_URL", "http://127.0.0.1:4173"),
    )
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--write-baseline", type=Path)
    parser.add_argument("--repeats", type=int)
    parser.add_argument("--loops", type=int)
    parser.add_argument("--audio", choices=("off", "on", "both"), default="both")
    parser.add_argument("--repair-applied", action="store_true")
    parser.add_argument("--confirmation", action="store_true")
    parser.add_argument("--quick", action="store_true")
    return parser.parse_args()


def git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def severity(status: str) -> int:
    return {"pass": 0, "baseline": 0, "warn": 1, "fail": 2, "invalid": 3}.get(
        status, 3
    )


def resolve_scenario_status(
    *,
    quality_status: str,
    comparison_status: str | None,
    creating_baseline: bool,
) -> str:
    """Keep absolute defects visible while applying a relative comparison."""
    normalized_comparison = (
        "invalid" if comparison_status == "incompatible" else comparison_status
    )
    if normalized_comparison is not None:
        return max(
            (quality_status, normalized_comparison),
            key=severity,
        )
    if creating_baseline and quality_status == "pass":
        return "baseline"
    return quality_status


def baseline_is_writable(run_report: dict[str, Any]) -> bool:
    """A warning may seed a diagnostic baseline; fatal/invalid data may not."""
    scenarios = list((run_report.get("scenarios") or {}).values())
    return bool(scenarios) and all(
        scenario.get("status") in {"baseline", "warn"}
        for scenario in scenarios
    )


def exit_code_for_status(status: str) -> int:
    return 2 if status in {"fail", "invalid"} else 0


def select_campaign_history(
    history: list[dict[str, Any]], campaign_id: str
) -> list[dict[str, Any]]:
    return [entry for entry in history if entry.get("campaignId") == campaign_id]


def run_repeat(
    browser,
    *,
    base_url: str,
    policy: dict[str, Any],
    audio_mode: str,
    loops: int,
    run_dir: Path,
    repeat_index: int,
) -> dict[str, Any]:
    scenario_policy = policy["scenario"]
    viewport_width, viewport_height = scenario_policy["viewport"]
    context = browser.new_context(
        viewport={"width": viewport_width, "height": viewport_height},
        device_scale_factor=scenario_policy["deviceScaleFactor"],
    )
    try:
        return _run_repeat_in_context(
            context,
            browser=browser,
            base_url=base_url,
            policy=policy,
            audio_mode=audio_mode,
            loops=loops,
            run_dir=run_dir,
            repeat_index=repeat_index,
        )
    finally:
        context.close()


def _run_repeat_in_context(
    context,
    *,
    browser,
    base_url: str,
    policy: dict[str, Any],
    audio_mode: str,
    loops: int,
    run_dir: Path,
    repeat_index: int,
) -> dict[str, Any]:
    scenario_policy = policy["scenario"]
    viewport_width, viewport_height = scenario_policy["viewport"]
    page = context.new_page()
    page.set_default_timeout(30000)
    console_errors: list[str] = []
    page_errors: list[str] = []
    resource_errors: list[str] = []
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on(
        "response",
        lambda response: resource_errors.append(
            f"HTTP {response.status} {response.url}"
        )
        if response.status >= 400 and not response.url.endswith("/favicon.ico")
        else None,
    )
    page.on(
        "requestfailed",
        lambda request: resource_errors.append(
            f"REQUEST FAILED {request.url}: {request.failure}"
        ),
    )
    page.add_init_script(PROBE_INIT_SCRIPT)
    page.goto(f"{base_url}/?variant={scenario_policy['variant']}")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector('body[data-ready="true"]')
    page.wait_for_function(
        "() => Number(getComputedStyle(document.querySelector('#stage-loading')).opacity) < 0.01"
    )
    metadata = page.evaluate(INSTALL_ENGINE_PROBE)
    page.wait_for_timeout(scenario_policy["warmupMs"])

    audio_start = None
    if audio_mode == "on":
        page.locator("#audio-file").set_input_files(str(AUDIO_FIXTURE.resolve()))
        page.wait_for_function(
            "() => document.querySelector('#audio-status').dataset.state === 'ready'"
        )
        page.locator("#audio-toggle").click()
        page.wait_for_function(
            "() => window.__AUDIO_RMS__.isPlaying && window.__AUDIO_RMS__.context?.state === 'running'"
        )
        audio_start = page.evaluate("() => window.__AUDIO_RMS__.audio.currentTime")

    script_duration = page.evaluate("() => window.__PUPPET__.script.duration")
    expected_duration_ms = script_duration * loops * 1000
    page.evaluate(
        """() => {
          Math.random = () => 0.5;
          const engine = window.__PUPPET__;
          engine.nextBlinkAt = engine.getSessionElapsed() + 2.4;
          window.__MOTION_PROBE__.start();
          engine.restart();
        }"""
    )
    page.wait_for_timeout(expected_duration_ms + 250)
    raw = page.evaluate("() => window.__MOTION_PROBE__.stop()")
    audio_end = page.evaluate(
        """() => ({
          isPlaying: window.__AUDIO_RMS__.isPlaying,
          contextState: window.__AUDIO_RMS__.context?.state ?? null,
          currentTime: window.__AUDIO_RMS__.audio?.currentTime ?? null,
          maxLevel: Math.max(0, ...window.__MOTION_PROBE__.samples.map((sample) => sample.audioLevel || 0)),
        })"""
    )
    screenshot_path = run_dir / f"audio-{audio_mode}-repeat-{repeat_index + 1}.png"
    page.screenshot(path=str(screenshot_path), full_page=False)

    samples = raw["samples"]
    for sample in samples:
        sample["loopIndex"] = min(
            loops - 1,
            max(0, int(float(sample.get("atMs", 0)) // (script_duration * 1000))),
        )
    summary = summarize_motion_samples(samples, long_tasks=raw["longTasks"])
    summary["tickerIntervals"] = summary["frameIntervals"]
    summary["frameIntervals"] = summarize_frame_intervals(
        entry["deltaMs"] for entry in raw["raf"]
    )
    summary["tickCpu"] = summarize_frame_intervals(
        entry["cpuMs"] for entry in raw["ticks"]
    )
    summary["tickerDelta"] = summarize_frame_intervals(
        entry["deltaMs"] for entry in raw["ticks"]
    )
    summary["longAnimationFrames"] = {
        "count": len(raw["longFrames"]),
        "totalBlockingMs": round(
            sum(float(entry.get("blockingDuration") or 0) for entry in raw["longFrames"]),
            3,
        ),
    }
    for phase, start_ms, end_ms in (
        ("cold", 0, script_duration * 1000),
        ("warm", script_duration * 1000, expected_duration_ms + 1000),
    ):
        summary[f"{phase}FrameIntervals"] = summarize_frame_intervals(
            entry["deltaMs"]
            for entry in raw["raf"]
            if start_ms <= entry["atMs"] < end_ms
        )

    p50 = summary["frameIntervals"].get("p50Ms") or 0
    refresh_bucket = round((1000 / p50) / 10) * 10 if p50 > 0 else None
    browser_version = browser.version
    environment = {
        "browser": "chrome",
        "browserVersion": browser_version,
        "browserMajor": browser_version.split(".")[0],
        "viewport": f"{viewport_width}x{viewport_height}",
        "deviceScaleFactor": scenario_policy["deviceScaleFactor"],
        "headless": True,
        "audio": audio_mode,
        "platform": platform.platform(),
        "webglVendor": metadata["webglVendor"],
        "webglRenderer": metadata["webglRenderer"],
        "observedRefreshRateHz": refresh_bucket,
    }
    renderer_invalid = any(
        pattern.lower() in metadata["webglRenderer"].lower()
        for pattern in policy["measurement"]["invalidateRendererPatterns"]
    )
    audio_valid = audio_mode == "off" or (
        bool(audio_end["isPlaying"])
        and audio_end["contextState"] == "running"
        and audio_start is not None
        and audio_end["currentTime"] is not None
        and audio_end["currentTime"] > audio_start
        and audio_end["maxLevel"] > 0
    )
    report = {
        "environment": environment,
        "metadata": {
            **metadata,
            "textureRgbaMiB": round(metadata["textureRgbaBytes"] / 1024 / 1024, 3),
            "scriptDurationSeconds": script_duration,
            "loops": loops,
        },
        "summary": summary,
        "runtime": {
            "consoleErrors": [
                error
                for error in console_errors
                if not error.startswith("Failed to load resource:")
            ]
            + resource_errors,
            "ignoredConsoleErrors": [
                error
                for error in console_errors
                if error.startswith("Failed to load resource:")
            ],
            "pageErrors": page_errors,
            "audio": {**audio_end, "valid": audio_valid},
        },
        "integrity": {
            "blackoutCount": raw["blackoutCount"],
            "invalidStateCount": raw["invalidStateCount"],
            "rendererValid": not renderer_invalid,
        },
        "diagnostics": {
            "topRafGaps": sorted(
                raw["raf"], key=lambda entry: entry["deltaMs"], reverse=True
            )[:10],
            "longTasks": raw["longTasks"],
            "longAnimationFrames": raw["longFrames"],
            "heapDeltaBytes": (
                raw["heapEnd"] - raw["heapStart"]
                if raw["heapStart"] is not None and raw["heapEnd"] is not None
                else None
            ),
        },
        "artifacts": {"screenshot": str(screenshot_path.relative_to(ROOT))},
    }
    quality = evaluate_motion_report(
        report,
        expected_duration_ms=expected_duration_ms,
        goals=policy["measurement"]["goals"],
    )
    if renderer_invalid:
        quality = {
            **quality,
            "status": "invalid",
            "reasons": ["software-webgl-renderer", *quality["reasons"]],
            "repairEligible": False,
        }
    elif not audio_valid:
        quality = {
            **quality,
            "status": "fail",
            "reasons": ["audio-probe-invalid", *quality["reasons"]],
            "repairEligible": False,
        }
    elif raw["invalidStateCount"]:
        quality = {
            **quality,
            "status": "fail",
            "reasons": ["nonfinite-motion-state", *quality["reasons"]],
            "repairEligible": False,
        }
    report["quality"] = quality

    trace_path = run_dir / f"audio-{audio_mode}-repeat-{repeat_index + 1}.ndjson"
    with trace_path.open("w", encoding="utf-8") as trace:
        for sample in samples:
            trace.write(json.dumps(sample, ensure_ascii=False, separators=(",", ":")))
            trace.write("\n")
    report["artifacts"]["trace"] = str(trace_path.relative_to(ROOT))
    return report


def main() -> int:
    args = parse_args()
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    if not AUDIO_FIXTURE.exists() and args.audio in {"on", "both"}:
        raise FileNotFoundError(AUDIO_FIXTURE)

    repeats = args.repeats or policy["measurement"]["monitorRepeats"]
    loops = args.loops or policy["scenario"]["captureLoops"]
    if args.quick:
        repeats = 1
        loops = 1
        args.audio = "off"
    if repeats < 1 or loops < 1:
        raise ValueError("repeats and loops must be positive")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    output_root = args.output_root.resolve()
    run_dir = output_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    audio_modes = ["off", "on"] if args.audio == "both" else [args.audio]
    baseline = load_json(args.baseline)
    creating_baseline = args.write_baseline is not None
    campaign_id = (
        (baseline or {}).get("run", {}).get("campaignId")
        or (baseline or {}).get("run", {}).get("id")
        or run_id
    )

    run_report: dict[str, Any] = {
        "schemaVersion": policy["schemaVersion"],
        "run": {
            "id": run_id,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "gitCommit": git_value("rev-parse", "HEAD"),
            "gitDirty": bool(git_value("status", "--porcelain")),
            "profile": "system-chrome-headless",
            "policy": str(args.policy.resolve().relative_to(ROOT)),
            "repairApplied": args.repair_applied,
            "confirmation": args.confirmation,
            "campaignId": campaign_id,
        },
        "scenarios": {},
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            channel=policy["measurement"]["browserChannel"],
            headless=True,
            args=[
                "--enable-precise-memory-info",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
            ],
        )
        try:
            for audio_mode in audio_modes:
                reports = [
                    run_repeat(
                        browser,
                        base_url=args.base_url.rstrip("/"),
                        policy=policy,
                        audio_mode=audio_mode,
                        loops=loops,
                        run_dir=run_dir,
                        repeat_index=repeat_index,
                    )
                    for repeat_index in range(repeats)
                ]
                aggregate = aggregate_motion_reports(reports)
                expected_duration_ms = (
                    reports[0]["metadata"]["scriptDurationSeconds"] * loops * 1000
                )
                quality = evaluate_motion_report(
                    aggregate,
                    expected_duration_ms=expected_duration_ms,
                    goals=policy["measurement"]["goals"],
                )
                repeat_statuses = [report["quality"]["status"] for report in reports]
                if "invalid" in repeat_statuses:
                    quality["status"] = "invalid"
                    quality["reasons"] = [
                        "invalid-repeat-environment",
                        *quality["reasons"],
                    ]
                elif "fail" in repeat_statuses:
                    quality["status"] = "fail"
                    quality["reasons"] = ["failed-repeat", *quality["reasons"]]

                comparison = None
                baseline_scenario = (baseline or {}).get("scenarios", {}).get(
                    f"whisper-audio-{audio_mode}"
                )
                if baseline_scenario:
                    comparison = compare_motion_reports(
                        aggregate, baseline_scenario["aggregate"]
                    )
                    status = resolve_scenario_status(
                        quality_status=quality["status"],
                        comparison_status=comparison["status"],
                        creating_baseline=False,
                    )
                elif baseline is not None:
                    status = "invalid"
                    comparison = {
                        "compatible": False,
                        "status": "incompatible",
                        "reasons": ["missing-baseline-scenario"],
                    }
                else:
                    status = resolve_scenario_status(
                        quality_status=quality["status"],
                        comparison_status=None,
                        creating_baseline=creating_baseline,
                    )

                repair_eligible = (
                    status in {"warn", "fail"}
                    and quality["status"] not in {"fail", "invalid"}
                )

                run_report["scenarios"][f"whisper-audio-{audio_mode}"] = {
                    "status": status,
                    "repairEligible": repair_eligible,
                    "aggregate": aggregate,
                    "qualityGoals": quality,
                    "comparison": comparison,
                    "repeats": reports,
                }
        finally:
            browser.close()

    statuses = [scenario["status"] for scenario in run_report["scenarios"].values()]
    overall_status = max(statuses, key=severity)
    run_report["overall"] = {
        "status": overall_status,
        "scenarioStatuses": {
            key: value["status"] for key, value in run_report["scenarios"].items()
        },
        "repairEligible": (
            overall_status in {"warn", "fail"}
            and any(
                value["repairEligible"]
                for value in run_report["scenarios"].values()
            )
            and not any(
                value["status"] == "invalid"
                for value in run_report["scenarios"].values()
            )
        ),
    }

    metrics_path = run_dir / "metrics.json"
    run_report["artifacts"] = {"metrics": str(metrics_path.relative_to(ROOT))}
    history_path = output_root / "history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_entry = {
        "runId": run_id,
        "createdAt": run_report["run"]["createdAt"],
        "gitCommit": run_report["run"]["gitCommit"],
        "status": overall_status,
        "campaignId": campaign_id,
        "isBaseline": creating_baseline,
        "confirmation": args.confirmation,
        "repairApplied": args.repair_applied,
        "repairEligible": run_report["overall"]["repairEligible"],
        "reasons": sorted(
            {
                reason
                for scenario in run_report["scenarios"].values()
                for source in (
                    scenario.get("qualityGoals") or {},
                    scenario.get("comparison") or {},
                )
                for reason in source.get("reasons", [])
            }
        ),
        "scenarioStatuses": run_report["overall"]["scenarioStatuses"],
        "metrics": str(metrics_path.relative_to(ROOT)),
    }
    with history_path.open("a", encoding="utf-8") as history:
        history.write(json.dumps(history_entry, ensure_ascii=False, separators=(",", ":")))
        history.write("\n")
    history_entries = [
        json.loads(line)
        for line in history_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    campaign_history = select_campaign_history(history_entries, campaign_id)
    run_report["overall"]["nextAction"] = decide_loop_action(
        campaign_history,
        max_repairs=policy["campaign"]["maxAutomaticRepairs"],
        clean_runs_to_stop=policy["campaign"]["cleanRunsToStop"],
        max_checks=policy["campaign"]["maxChecks"],
    )
    atomic_json(metrics_path, run_report)
    atomic_json(output_root / "latest.json", run_report)
    if args.write_baseline:
        if baseline_is_writable(run_report):
            run_report["baselineWritten"] = str(args.write_baseline.resolve())
            atomic_json(metrics_path, run_report)
            atomic_json(output_root / "latest.json", run_report)
            atomic_json(args.write_baseline.resolve(), run_report)
        else:
            run_report["baselineRejected"] = True
            atomic_json(metrics_path, run_report)
            atomic_json(output_root / "latest.json", run_report)

    compact = {
        "runId": run_id,
        "status": overall_status,
        "nextAction": run_report["overall"]["nextAction"],
        "metrics": str(metrics_path),
        "scenarios": {
            key: {
                "status": value["status"],
                "p95Ms": value["aggregate"]["summary"]["frameIntervals"]["p95Ms"],
                "p99Ms": value["aggregate"]["summary"]["frameIntervals"]["p99Ms"],
                "bodyMaxStep": value["aggregate"]["summary"]["bodyMotion"]["maxFrameStep"],
                "bodyTrackingP95": value["aggregate"]["summary"]["bodyMotion"].get(
                    "trackingError", {}
                ).get("p95"),
                "headTrackingP95": value["aggregate"]["summary"]["headMotion"].get(
                    "trackingError", {}
                ).get("p95"),
                "longTasks": value["aggregate"]["summary"]["longTasks"]["count"],
                "renderer": value["aggregate"]["environment"]["webglRenderer"],
            }
            for key, value in run_report["scenarios"].items()
        },
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return exit_code_for_status(overall_status)


if __name__ == "__main__":
    raise SystemExit(main())
