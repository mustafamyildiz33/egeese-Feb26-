#!/usr/bin/env python3
"""Phase-based paper evaluation runner for EGESS.

This runner reads a JSON phase specification, executes each requested demo with
an exact active scenario window, and writes Excel-friendly TSV plus Markdown
reports for the whole suite and for each individual run.
"""

import argparse
import json
import math
import os
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path
from urllib import request


ROOT_DIR = Path(__file__).resolve().parent
RUNS_DIR = ROOT_DIR / "runs"
REPORTS_DIR = ROOT_DIR / "paper_reports"


SUMMARY_FIELDS = [
    "suite_id",
    "phase_id",
    "phase_name",
    "protocol",
    "challenge",
    "duration_sec",
    "active_duration_sec",
    "nodes",
    "run_index",
    "seed",
    "run_dir",
    "local_watch_port",
    "far_watch_port",
    "reachable_nodes",
    "total_nodes",
    "events_total",
    "fault_ops",
    "trigger_ops",
    "pull_rx_total",
    "push_rx_total",
    "pull_tx_total",
    "push_tx_total",
    "rx_bytes_total",
    "tx_bytes_total",
    "total_bytes",
    "total_mb",
    "tx_ok_total",
    "tx_fail_total",
    "tx_timeout_total",
    "tx_conn_error_total",
    "status",
]


WATCH_FIELDS = [
    "suite_id",
    "phase_id",
    "phase_name",
    "protocol",
    "challenge",
    "duration_sec",
    "nodes",
    "run_index",
    "seed",
    "view",
    "watch_port",
    "reachable",
    "protocol_state",
    "boundary_kind",
    "score",
    "front_score",
    "impact_score",
    "arrest_score",
    "coherence_score",
    "accepted_messages",
    "pull_rx",
    "push_rx",
    "pull_tx",
    "push_tx",
    "rx_total_bytes",
    "tx_total_bytes",
    "total_bytes",
    "total_mb",
    "direction_label",
    "phase",
    "distance_hops",
    "eta_cycles",
    "current_missing_count",
    "crash_sim",
    "lie_sensor",
    "flap",
]


def _to_int(value, fallback):
    try:
        return int(value)
    except Exception:
        return int(fallback)


def _to_float(value, fallback):
    try:
        return float(value)
    except Exception:
        return float(fallback)


def _json_size_bytes(payload):
    """Return a compact UTF-8 JSON size for reporting."""
    try:
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    except Exception:
        body = json.dumps(str(payload))
    return int(len(body.encode("utf-8")))


def _auto_grid_size(number_of_nodes):
    root = int(math.isqrt(int(number_of_nodes)))
    if root > 0 and root * root == int(number_of_nodes):
        return int(root)
    root = int(math.ceil(math.sqrt(float(number_of_nodes))))
    if root < 2:
        root = 2
    return int(root)


def _port_to_rc(base_port, port, grid):
    idx = int(port) - int(base_port)
    return int(idx // grid), int(idx % grid)


def _rc_to_port(base_port, row, col, grid, number_of_nodes):
    if row < 0 or col < 0 or row >= grid or col >= grid:
        return None
    idx = row * grid + col
    if idx < 0 or idx >= int(number_of_nodes):
        return None
    return int(base_port) + idx


def _hex_neighbors_odd_r(col, row, grid):
    if row % 2 == 0:
        candidates = [
            (col - 1, row),
            (col + 1, row),
            (col, row - 1),
            (col - 1, row - 1),
            (col, row + 1),
            (col - 1, row + 1),
        ]
    else:
        candidates = [
            (col - 1, row),
            (col + 1, row),
            (col + 1, row - 1),
            (col, row - 1),
            (col + 1, row + 1),
            (col, row + 1),
        ]
    out = []
    for c, r in candidates:
        if 0 <= c < grid and 0 <= r < grid:
            out.append((c, r))
    return out


def _hex_center_xy(row, col):
    x = math.sqrt(3.0) * (float(col) + (0.5 if int(row) % 2 == 1 else 0.0))
    y = 1.5 * float(row)
    return x, y


def _farthest_port(base_port, number_of_nodes, reference_port):
    grid = _auto_grid_size(number_of_nodes)
    ref_row, ref_col = _port_to_rc(base_port, reference_port, grid)
    ref_x, ref_y = _hex_center_xy(ref_row, ref_col)
    best_port = int(reference_port)
    best_distance = -1.0
    for port in range(int(base_port), int(base_port) + int(number_of_nodes)):
        row, col = _port_to_rc(base_port, port, grid)
        x, y = _hex_center_xy(row, col)
        d2 = ((x - ref_x) ** 2) + ((y - ref_y) ** 2)
        if d2 > best_distance:
            best_distance = d2
            best_port = int(port)
    return int(best_port)


def _center_port(base_port, number_of_nodes):
    grid = _auto_grid_size(number_of_nodes)
    row = int(grid // 2)
    col = int(grid // 2)
    center = _rc_to_port(base_port, row, col, grid, number_of_nodes)
    if center is None:
        center = int(base_port) + max(0, (int(number_of_nodes) // 2))
    return int(center)


def _neighbors_for_port(base_port, number_of_nodes, port):
    grid = _auto_grid_size(number_of_nodes)
    row, col = _port_to_rc(base_port, port, grid)
    neighbors = []
    for ncol, nrow in _hex_neighbors_odd_r(col, row, grid):
        nport = _rc_to_port(base_port, nrow, ncol, grid, number_of_nodes)
        if nport is not None and int(nport) != int(port):
            neighbors.append(int(nport))
    return sorted(neighbors)


def _post_json(port, payload, timeout=1.0):
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        "http://127.0.0.1:{}/".format(int(port)),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _pull_state(port, origin="paper_eval", timeout=1.0):
    payload = {
        "op": "pull",
        "data": {"kind": "paper_eval"},
        "metadata": {"origin": str(origin)},
    }
    return _post_json(port, payload, timeout=timeout)


def _trigger_push(port, label, timeout=1.2):
    payload = {
        "op": "push",
        "data": {
            "type": "paper_eval_trigger",
            "label": str(label),
            "ts": float(time.time()),
        },
        "metadata": {
            "origin": int(port),
            "relay": 0,
            "forward_count": 0,
        },
    }
    return _post_json(port, payload, timeout=timeout)


def _inject_fault(port, fault, enable=True, period_sec=4, timeout=1.2):
    payload = {
        "op": "inject_fault",
        "data": {
            "fault": str(fault),
            "enable": bool(enable),
            "period_sec": int(period_sec),
        },
        "metadata": {"origin": "paper_eval"},
    }
    return _post_json(port, payload, timeout=timeout)


def _inject_state(port, sensor_state, timeout=1.2):
    payload = {
        "op": "inject_state",
        "data": {"sensor_state": str(sensor_state).strip().upper()},
        "metadata": {"origin": "paper_eval"},
    }
    return _post_json(port, payload, timeout=timeout)


def _append_jsonl(path, row):
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def _log_event(path, kind, data):
    row = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "kind": str(kind),
        "data": data,
    }
    _append_jsonl(path, row)


def _write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _write_tsv(path, rows, fields):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\t".join(fields) + "\n")
        for row in rows:
            values = []
            for field in fields:
                value = row.get(field, "")
                if isinstance(value, float):
                    value = "{:.3f}".format(value)
                elif isinstance(value, (dict, list)):
                    value = json.dumps(value, sort_keys=True)
                values.append(str(value))
            handle.write("\t".join(values) + "\n")


def _latest_run_dir():
    if not RUNS_DIR.exists():
        raise RuntimeError("runs directory does not exist yet")
    candidates = [path for path in RUNS_DIR.iterdir() if path.is_dir()]
    if not candidates:
        raise RuntimeError("no run directories exist yet")
    return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)[0]


def _stop_nodes():
    subprocess.run(["./stop_nodes.sh"], cwd=str(ROOT_DIR), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _start_nodes(number_of_nodes):
    env = os.environ.copy()
    env["EGESS_LOG"] = "1"
    subprocess.run(
        ["./start_nodes.sh", str(int(number_of_nodes))],
        cwd=str(ROOT_DIR),
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return _latest_run_dir()


def _wait_until_ready(base_port, number_of_nodes, timeout_sec=35.0):
    deadline = time.monotonic() + float(timeout_sec)
    while time.monotonic() < deadline:
        ready = 0
        for port in range(int(base_port), int(base_port) + int(number_of_nodes)):
            try:
                res = _pull_state(port, origin="bootstrap", timeout=0.8)
                if isinstance(res, dict) and res.get("op") == "receipt":
                    ready += 1
            except Exception:
                pass
        if ready >= int(number_of_nodes):
            return True
        time.sleep(1.0)
    return False


def _tornado_sweep_batches(base_port, number_of_nodes, seed, width):
    grid = _auto_grid_size(number_of_nodes)
    width = max(1, min(int(width), int(grid)))
    rng = random.Random(int(seed))
    direction = rng.randint(0, 3)
    batches = []

    if direction in (0, 1):
        start_row = rng.randint(0, grid - width)
        band_rows = list(range(start_row, start_row + width))
        for sweep_idx in range(grid):
            col = sweep_idx if direction == 0 else (grid - 1 - sweep_idx)
            ports = []
            for row in band_rows:
                port = _rc_to_port(base_port, row, col, grid, number_of_nodes)
                if port is not None:
                    ports.append(int(port))
            if ports:
                batches.append(sorted(ports))
    else:
        start_col = rng.randint(0, grid - width)
        band_cols = list(range(start_col, start_col + width))
        for sweep_idx in range(grid):
            row = sweep_idx if direction == 2 else (grid - 1 - sweep_idx)
            ports = []
            for col in band_cols:
                port = _rc_to_port(base_port, row, col, grid, number_of_nodes)
                if port is not None:
                    ports.append(int(port))
            if ports:
                batches.append(sorted(ports))

    return batches


def _baseline_actions(spec, base_port, number_of_nodes, seed):
    del spec, base_port, number_of_nodes, seed
    return []


def _tornado_actions(spec, base_port, number_of_nodes, seed):
    duration_sec = _to_float(spec.get("duration_sec", 60), 60.0)
    width = _to_int(spec.get("scenario", {}).get("tornado_width", 2), 2)
    batches = _tornado_sweep_batches(base_port, number_of_nodes, seed, width)
    actions = []
    if len(batches) == 0:
        return actions

    baseline_gap = max(2.0, duration_sec * 0.10)
    sweep_window = max(4.0, duration_sec * 0.60)
    step_gap = sweep_window / max(1, len(batches) - 1) if len(batches) > 1 else sweep_window
    killed_ports = sorted({port for batch in batches for port in batch})

    for idx, ports in enumerate(batches):
        actions.append(
            {
                "at_sec": round(baseline_gap + (idx * step_gap), 3),
                "kind": "crash_batch",
                "ports": [int(port) for port in ports],
                "label": "tornado_step_{}".format(idx + 1),
            }
        )

    recovery_at = min(duration_sec - 1.0, max(baseline_gap + sweep_window + 1.0, duration_sec * 0.78))
    reset_at = min(duration_sec - 0.2, max(recovery_at + 1.0, duration_sec * 0.93))
    actions.append(
        {
            "at_sec": round(recovery_at, 3),
            "kind": "recover_batch",
            "ports": killed_ports,
            "label": "tornado_recovery",
        }
    )
    actions.append(
        {
            "at_sec": round(reset_at, 3),
            "kind": "reset_batch",
            "ports": killed_ports,
            "label": "tornado_reset",
        }
    )
    return actions


def _stress_actions(spec, base_port, number_of_nodes, seed):
    del seed
    duration_sec = _to_float(spec.get("duration_sec", 60), 60.0)
    period_sec = _to_int(spec.get("scenario", {}).get("fault_period_sec", 4), 4)
    target = _center_port(base_port, number_of_nodes)
    neighbors = _neighbors_for_port(base_port, number_of_nodes, target)
    lie_port = int(neighbors[0]) if len(neighbors) > 0 else int(target)
    flap_port = int(neighbors[1]) if len(neighbors) > 1 else int(lie_port)
    actions = [
        {
            "at_sec": round(duration_sec * 0.15, 3),
            "kind": "fault_toggle",
            "port": int(target),
            "fault": "crash_sim",
            "enable": True,
            "period_sec": period_sec,
            "label": "ghost_outage_on",
        },
        {
            "at_sec": round(duration_sec * 0.28, 3),
            "kind": "fault_toggle",
            "port": int(target),
            "fault": "crash_sim",
            "enable": False,
            "period_sec": period_sec,
            "label": "ghost_outage_off",
        },
        {
            "at_sec": round(duration_sec * 0.40, 3),
            "kind": "fault_toggle",
            "port": int(lie_port),
            "fault": "lie_sensor",
            "enable": True,
            "period_sec": period_sec,
            "label": "lie_sensor_on",
        },
        {
            "at_sec": round(duration_sec * 0.55, 3),
            "kind": "fault_toggle",
            "port": int(lie_port),
            "fault": "lie_sensor",
            "enable": False,
            "period_sec": period_sec,
            "label": "lie_sensor_off",
        },
        {
            "at_sec": round(duration_sec * 0.62, 3),
            "kind": "fault_toggle",
            "port": int(flap_port),
            "fault": "flap",
            "enable": True,
            "period_sec": max(2, period_sec),
            "label": "flap_on",
        },
        {
            "at_sec": round(duration_sec * 0.82, 3),
            "kind": "fault_toggle",
            "port": int(flap_port),
            "fault": "flap",
            "enable": False,
            "period_sec": max(2, period_sec),
            "label": "flap_off",
        },
        {
            "at_sec": round(duration_sec * 0.88, 3),
            "kind": "state_batch",
            "ports": [int(target), int(lie_port), int(flap_port)],
            "sensor_state": "RECOVERING",
            "label": "stress_recovering",
        },
        {
            "at_sec": round(duration_sec * 0.96, 3),
            "kind": "reset_batch",
            "ports": [int(target), int(lie_port), int(flap_port)],
            "label": "stress_reset",
        },
    ]
    return actions


def _scenario_actions(spec, base_port, number_of_nodes, seed):
    kind = str(spec.get("scenario", {}).get("kind", "baseline")).strip().lower()
    if kind == "baseline":
        return _baseline_actions(spec, base_port, number_of_nodes, seed)
    if kind == "tornado_sweep":
        return _tornado_actions(spec, base_port, number_of_nodes, seed)
    if kind == "ghost_outage_noise":
        return _stress_actions(spec, base_port, number_of_nodes, seed)
    raise ValueError("unsupported scenario kind: {}".format(kind))


def _watch_ports(spec, base_port, number_of_nodes, seed):
    kind = str(spec.get("scenario", {}).get("kind", "baseline")).strip().lower()
    if kind == "tornado_sweep":
        batches = _tornado_sweep_batches(base_port, number_of_nodes, seed, spec.get("scenario", {}).get("tornado_width", 2))
        local_watch = int(batches[0][0]) if len(batches) > 0 and len(batches[0]) > 0 else _center_port(base_port, number_of_nodes)
    elif kind == "ghost_outage_noise":
        local_watch = _center_port(base_port, number_of_nodes)
    else:
        local_watch = _center_port(base_port, number_of_nodes)

    far_watch = _farthest_port(base_port, number_of_nodes, local_watch)
    if int(far_watch) == int(local_watch) and int(number_of_nodes) > 1:
        far_watch = int(base_port) + int(number_of_nodes) - 1
    return {
        "LOCAL": int(local_watch),
        "FAR": int(far_watch),
    }


def _apply_action(action, events_path):
    kind = str(action.get("kind", ""))
    label = str(action.get("label", kind))

    if kind == "crash_batch":
        for port in action.get("ports", []):
            res = _inject_fault(port, "crash_sim", True, period_sec=action.get("period_sec", 4))
            _log_event(events_path, "fault", {"label": label, "port": int(port), "fault": "crash_sim", "enable": True, "response": res})
        return

    if kind == "recover_batch":
        for port in action.get("ports", []):
            res_fault = _inject_fault(port, "crash_sim", False, period_sec=action.get("period_sec", 4))
            res_state = _inject_state(port, "RECOVERING")
            _log_event(events_path, "fault", {"label": label, "port": int(port), "fault": "crash_sim", "enable": False, "response": res_fault})
            _log_event(events_path, "state", {"label": label, "port": int(port), "sensor_state": "RECOVERING", "response": res_state})
        return

    if kind == "reset_batch":
        for port in action.get("ports", []):
            res_reset = _inject_fault(port, "reset", True, period_sec=action.get("period_sec", 4))
            res_state = _inject_state(port, "NORMAL")
            _log_event(events_path, "fault", {"label": label, "port": int(port), "fault": "reset", "enable": True, "response": res_reset})
            _log_event(events_path, "state", {"label": label, "port": int(port), "sensor_state": "NORMAL", "response": res_state})
        return

    if kind == "fault_toggle":
        res = _inject_fault(
            action.get("port"),
            action.get("fault"),
            bool(action.get("enable", True)),
            period_sec=action.get("period_sec", 4),
        )
        _log_event(
            events_path,
            "fault",
            {
                "label": label,
                "port": int(action.get("port")),
                "fault": str(action.get("fault")),
                "enable": bool(action.get("enable", True)),
                "period_sec": int(action.get("period_sec", 4)),
                "response": res,
            },
        )
        return

    if kind == "state_batch":
        for port in action.get("ports", []):
            res = _inject_state(port, action.get("sensor_state", "NORMAL"))
            _log_event(events_path, "state", {"label": label, "port": int(port), "sensor_state": str(action.get("sensor_state", "NORMAL")), "response": res})
        return

    raise ValueError("unsupported action kind: {}".format(kind))


def _run_active_window(spec, base_port, number_of_nodes, run_index, seed, events_path):
    duration_sec = _to_float(spec.get("duration_sec", 60), 60.0)
    trigger_interval_sec = max(0.25, _to_float(spec.get("trigger_interval_sec", 2), 2.0))
    ports = list(range(int(base_port), int(base_port) + int(number_of_nodes)))
    actions = sorted(_scenario_actions(spec, base_port, number_of_nodes, seed), key=lambda item: float(item.get("at_sec", 0.0)))

    start = time.monotonic()
    deadline = start + float(duration_sec)
    next_trigger = start
    trigger_index = 0
    action_index = 0

    _log_event(events_path, "stage", {"name": "active_window_start", "duration_sec": duration_sec})

    while True:
        now = time.monotonic()
        if now >= deadline:
            break

        elapsed = now - start
        while action_index < len(actions) and elapsed >= float(actions[action_index].get("at_sec", 0.0)):
            _apply_action(actions[action_index], events_path)
            action_index += 1

        if now >= next_trigger:
            port = ports[trigger_index % len(ports)]
            label = "{}_run{}_idx{}".format(str(spec.get("challenge", "demo")), int(run_index), int(trigger_index))
            try:
                res = _trigger_push(port, label)
                ok = bool(res.get("data", {}).get("success", False))
                _log_event(events_path, "trigger", {"port": int(port), "label": label, "ok": ok, "response": res})
            except Exception as exc:
                _log_event(events_path, "trigger_error", {"port": int(port), "label": label, "error": str(exc)})
            trigger_index += 1
            next_trigger += float(trigger_interval_sec)

        remaining = max(0.0, deadline - time.monotonic())
        time.sleep(min(0.05, remaining if remaining > 0.0 else 0.0))

    active_duration_sec = round(float(time.monotonic() - start), 3)

    # Final cleanup keeps the next run isolated from whatever fault pattern just ran.
    watch_ports = _watch_ports(spec, base_port, number_of_nodes, seed)
    cleanup_ports = sorted(set([int(port) for port in watch_ports.values()]))
    for action in actions:
        if isinstance(action.get("ports"), list):
            cleanup_ports.extend(int(port) for port in action.get("ports", []))
        if "port" in action:
            cleanup_ports.append(int(action.get("port")))
    for port in sorted(set(cleanup_ports)):
        try:
            _inject_fault(port, "reset", True, period_sec=4)
            _inject_state(port, "NORMAL")
        except Exception:
            pass

    _log_event(events_path, "done", {"active_duration_sec": active_duration_sec, "trigger_count": int(trigger_index)})
    return active_duration_sec, int(trigger_index)


def _collect_evidence(spec, run_dir, events_path, base_port, number_of_nodes, run_index, seed, active_duration_sec):
    totals = {
        "pull_rx": 0,
        "push_rx": 0,
        "pull_tx": 0,
        "push_tx": 0,
        "pull_rx_bytes": 0,
        "push_rx_bytes": 0,
        "pull_tx_bytes": 0,
        "push_tx_bytes": 0,
        "rx_total_bytes": 0,
        "tx_total_bytes": 0,
        "tx_ok": 0,
        "tx_fail": 0,
        "tx_timeout": 0,
        "tx_conn_error": 0,
    }
    nodes = {}
    reachable = 0

    for port in range(int(base_port), int(base_port) + int(number_of_nodes)):
        try:
            res = _pull_state(port, origin="paper_report", timeout=1.0)
            state = res.get("data", {}).get("node_state", {}) if isinstance(res, dict) else {}
            counters = state.get("msg_counters", {})
            if not isinstance(counters, dict):
                counters = {}
            for key in totals:
                totals[key] += _to_int(counters.get(key, 0), 0)
            nodes[str(port)] = {
                "reachable": True,
                "state": state,
                "msg_counters": counters,
            }
            reachable += 1
        except Exception as exc:
            nodes[str(port)] = {
                "reachable": False,
                "error": str(exc),
            }

    event_counts = {
        "events_total": 0,
        "fault_ops": 0,
        "trigger_ops": 0,
        "state_ops": 0,
    }
    with open(events_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if len(line) == 0:
                continue
            event_counts["events_total"] += 1
            row = json.loads(line)
            kind = str(row.get("kind", ""))
            if kind in ("fault", "fault_error"):
                event_counts["fault_ops"] += 1
            elif kind in ("trigger", "trigger_error"):
                event_counts["trigger_ops"] += 1
            elif kind == "state":
                event_counts["state_ops"] += 1

    watch_ports = _watch_ports(spec, base_port, number_of_nodes, seed)
    watch_rows = []
    for view, port in watch_ports.items():
        node_info = nodes.get(str(port), {"reachable": False})
        state = node_info.get("state", {})
        counters = node_info.get("msg_counters", {})
        layer2 = state.get("layer2_confirmation", {}) if isinstance(state, dict) else {}
        faults = state.get("faults", {}) if isinstance(state, dict) else {}
        total_bytes = _to_int(counters.get("rx_total_bytes", 0), 0) + _to_int(counters.get("tx_total_bytes", 0), 0)
        watch_rows.append(
            {
                "suite_id": str(spec.get("suite_id", "")),
                "phase_id": str(spec.get("phase_id", "")),
                "phase_name": str(spec.get("phase_name", "")),
                "protocol": str(spec.get("protocol", "")),
                "challenge": str(spec.get("challenge", "")),
                "duration_sec": _to_int(spec.get("duration_sec", 60), 60),
                "nodes": int(number_of_nodes),
                "run_index": int(run_index),
                "seed": int(seed),
                "view": str(view),
                "watch_port": int(port),
                "reachable": bool(node_info.get("reachable", False)),
                "protocol_state": str(state.get("protocol_state", "")),
                "boundary_kind": str(state.get("boundary_kind", "")),
                "score": _to_float(state.get("score", 0.0), 0.0),
                "front_score": _to_float(state.get("front_score", 0.0), 0.0),
                "impact_score": _to_float(state.get("impact_score", 0.0), 0.0),
                "arrest_score": _to_float(state.get("arrest_score", 0.0), 0.0),
                "coherence_score": _to_int(state.get("coherence_score", 0), 0),
                "accepted_messages": _to_int(state.get("accepted_messages", 0), 0),
                "pull_rx": _to_int(counters.get("pull_rx", 0), 0),
                "push_rx": _to_int(counters.get("push_rx", 0), 0),
                "pull_tx": _to_int(counters.get("pull_tx", 0), 0),
                "push_tx": _to_int(counters.get("push_tx", 0), 0),
                "rx_total_bytes": _to_int(counters.get("rx_total_bytes", 0), 0),
                "tx_total_bytes": _to_int(counters.get("tx_total_bytes", 0), 0),
                "total_bytes": int(total_bytes),
                "total_mb": round(float(total_bytes) / 1048576.0, 3),
                "direction_label": str(layer2.get("direction_label", "")),
                "phase": str(layer2.get("phase", "")),
                "distance_hops": _to_float(layer2.get("distance_hops", 99.0), 99.0),
                "eta_cycles": _to_float(layer2.get("eta_cycles", 99.0), 99.0),
                "current_missing_count": len(state.get("current_missing_neighbors", [])) if isinstance(state.get("current_missing_neighbors"), list) else 0,
                "crash_sim": bool(faults.get("crash_sim", False)),
                "lie_sensor": bool(faults.get("lie_sensor", False)),
                "flap": bool(faults.get("flap", False)),
            }
        )

    total_bytes = int(totals["rx_total_bytes"]) + int(totals["tx_total_bytes"])
    summary_row = {
        "suite_id": str(spec.get("suite_id", "")),
        "phase_id": str(spec.get("phase_id", "")),
        "phase_name": str(spec.get("phase_name", "")),
        "protocol": str(spec.get("protocol", "")),
        "challenge": str(spec.get("challenge", "")),
        "duration_sec": _to_int(spec.get("duration_sec", 60), 60),
        "active_duration_sec": float(active_duration_sec),
        "nodes": int(number_of_nodes),
        "run_index": int(run_index),
        "seed": int(seed),
        "run_dir": str(run_dir.relative_to(ROOT_DIR)),
        "local_watch_port": int(watch_ports["LOCAL"]),
        "far_watch_port": int(watch_ports["FAR"]),
        "reachable_nodes": int(reachable),
        "total_nodes": int(number_of_nodes),
        "events_total": int(event_counts["events_total"]),
        "fault_ops": int(event_counts["fault_ops"]),
        "trigger_ops": int(event_counts["trigger_ops"]),
        "pull_rx_total": int(totals["pull_rx"]),
        "push_rx_total": int(totals["push_rx"]),
        "pull_tx_total": int(totals["pull_tx"]),
        "push_tx_total": int(totals["push_tx"]),
        "rx_bytes_total": int(totals["rx_total_bytes"]),
        "tx_bytes_total": int(totals["tx_total_bytes"]),
        "total_bytes": int(total_bytes),
        "total_mb": round(float(total_bytes) / 1048576.0, 3),
        "tx_ok_total": int(totals["tx_ok"]),
        "tx_fail_total": int(totals["tx_fail"]),
        "tx_timeout_total": int(totals["tx_timeout"]),
        "tx_conn_error_total": int(totals["tx_conn_error"]),
        "status": "OK" if int(reachable) == int(number_of_nodes) else "WARN",
    }

    manifest = {
        "suite_id": str(spec.get("suite_id", "")),
        "phase_id": str(spec.get("phase_id", "")),
        "phase_name": str(spec.get("phase_name", "")),
        "protocol": str(spec.get("protocol", "")),
        "challenge": str(spec.get("challenge", "")),
        "duration_sec": _to_int(spec.get("duration_sec", 60), 60),
        "active_duration_sec": float(active_duration_sec),
        "nodes": int(number_of_nodes),
        "run_index": int(run_index),
        "seed": int(seed),
        "watch_ports": watch_ports,
        "spec_path": str(spec.get("_spec_path", "")),
    }

    return manifest, summary_row, watch_rows, {"nodes": nodes, "totals": totals, "event_counts": event_counts}


def _write_run_reports(run_dir, manifest, summary_row, watch_rows, evidence, events_path):
    manifest_path = run_dir / "paper_manifest.json"
    summary_tsv_path = run_dir / "paper_summary.tsv"
    watch_tsv_path = run_dir / "paper_watch_nodes.tsv"
    evidence_path = run_dir / "paper_evidence.json"
    summary_md_path = run_dir / "paper_summary.md"

    _write_json(manifest_path, manifest)
    _write_json(evidence_path, evidence)
    _write_tsv(summary_tsv_path, [summary_row], SUMMARY_FIELDS)
    _write_tsv(watch_tsv_path, watch_rows, WATCH_FIELDS)

    lines = [
        "# {}".format(manifest.get("phase_name", "Paper Evaluation Run")),
        "",
        "- Phase: `{}`".format(manifest.get("phase_id", "")),
        "- Challenge: `{}`".format(summary_row.get("challenge", "")),
        "- Nodes: `{}`".format(summary_row.get("nodes", "")),
        "- Duration (requested / active): `{}` / `{}` seconds".format(summary_row.get("duration_sec", ""), summary_row.get("active_duration_sec", "")),
        "- Run index / seed: `{}` / `{}`".format(summary_row.get("run_index", ""), summary_row.get("seed", "")),
        "- Local / Far watch ports: `{}` / `{}`".format(summary_row.get("local_watch_port", ""), summary_row.get("far_watch_port", "")),
        "- Reachable nodes: `{}` / `{}`".format(summary_row.get("reachable_nodes", ""), summary_row.get("total_nodes", "")),
        "- Message totals (pull rx, push rx, pull tx, push tx): `{}`, `{}`, `{}`, `{}`".format(
            summary_row.get("pull_rx_total", ""),
            summary_row.get("push_rx_total", ""),
            summary_row.get("pull_tx_total", ""),
            summary_row.get("push_tx_total", ""),
        ),
        "- Byte totals (rx, tx, combined MB): `{}`, `{}`, `{}`".format(
            summary_row.get("rx_bytes_total", ""),
            summary_row.get("tx_bytes_total", ""),
            summary_row.get("total_mb", ""),
        ),
        "- Failure totals (fail / timeout / conn_error): `{}` / `{}` / `{}`".format(
            summary_row.get("tx_fail_total", ""),
            summary_row.get("tx_timeout_total", ""),
            summary_row.get("tx_conn_error_total", ""),
        ),
        "- Events JSONL: `{}`".format(str(Path(events_path).name)),
        "- Summary TSV: `{}`".format(summary_tsv_path.name),
        "- Watch TSV: `{}`".format(watch_tsv_path.name),
    ]
    with open(summary_md_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _suite_case_rows(spec, max_runs=None, node_counts_override=None):
    node_counts = spec.get("node_counts", [])
    if node_counts_override:
        node_counts = [int(value) for value in node_counts_override]
    run_count = _to_int(spec.get("run_count", 1), 1)
    if max_runs is not None:
        run_count = min(int(run_count), int(max_runs))
    base_seed = _to_int(spec.get("seed_base", 1000), 1000)
    rows = []
    for node_count in node_counts:
        for run_index in range(1, int(run_count) + 1):
            rows.append(
                {
                    "nodes": int(node_count),
                    "run_index": int(run_index),
                    "seed": int(base_seed + run_index - 1),
                }
            )
    return rows


def _suite_summary_rows(summary_rows):
    groups = {}
    for row in summary_rows:
        key = (row["phase_id"], row["challenge"], row["duration_sec"], row["nodes"])
        groups.setdefault(key, []).append(row)

    out = []
    for key, rows in sorted(groups.items()):
        totals_mb = [float(item.get("total_mb", 0.0)) for item in rows]
        push_rx_total = [int(item.get("push_rx_total", 0)) for item in rows]
        tx_fail_total = [int(item.get("tx_fail_total", 0)) for item in rows]
        out.append(
            {
                "phase_id": key[0],
                "challenge": key[1],
                "duration_sec": key[2],
                "nodes": key[3],
                "runs": len(rows),
                "avg_total_mb": round(statistics.mean(totals_mb), 3) if totals_mb else 0.0,
                "avg_push_rx_total": round(statistics.mean(push_rx_total), 3) if push_rx_total else 0.0,
                "avg_tx_fail_total": round(statistics.mean(tx_fail_total), 3) if tx_fail_total else 0.0,
            }
        )
    return out


def _write_suite_reports(report_dir, spec, summary_rows, watch_rows):
    all_runs_tsv = report_dir / "all_runs.tsv"
    all_watch_tsv = report_dir / "all_watch_nodes.tsv"
    summary_by_nodes_tsv = report_dir / "summary_by_nodes.tsv"
    summary_md = report_dir / "README.md"

    _write_tsv(all_runs_tsv, summary_rows, SUMMARY_FIELDS)
    _write_tsv(all_watch_tsv, watch_rows, WATCH_FIELDS)

    summary_by_nodes_rows = _suite_summary_rows(summary_rows)
    summary_by_nodes_fields = ["phase_id", "challenge", "duration_sec", "nodes", "runs", "avg_total_mb", "avg_push_rx_total", "avg_tx_fail_total"]
    _write_tsv(summary_by_nodes_tsv, summary_by_nodes_rows, summary_by_nodes_fields)

    lines = [
        "# {}".format(spec.get("phase_name", "Paper Evaluation Suite")),
        "",
        "- Suite ID: `{}`".format(spec.get("suite_id", "")),
        "- Protocol: `{}`".format(spec.get("protocol", "")),
        "- Challenge: `{}`".format(spec.get("challenge", "")),
        "- Runs completed: `{}`".format(len(summary_rows)),
        "- Aggregate run table: `all_runs.tsv`",
        "- Watch-node table: `all_watch_nodes.tsv`",
        "- Grouped summary: `summary_by_nodes.tsv`",
    ]
    with open(summary_md, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _load_spec(path):
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    payload["_spec_path"] = str(path)
    return payload


def _validate_spec(spec):
    if str(spec.get("protocol", "")).strip().lower() != "egess":
        raise ValueError("only protocol='egess' is supported by this runner right now")
    if not isinstance(spec.get("node_counts", []), list) or len(spec.get("node_counts", [])) == 0:
        raise ValueError("spec must define a non-empty node_counts list")
    if _to_int(spec.get("run_count", 0), 0) < 1:
        raise ValueError("spec run_count must be >= 1")
    if _to_int(spec.get("duration_sec", 0), 0) < 1:
        raise ValueError("spec duration_sec must be >= 1")
    if str(spec.get("phase_id", "")).strip() == "":
        raise ValueError("spec phase_id is required")
    if str(spec.get("suite_id", "")).strip() == "":
        raise ValueError("spec suite_id is required")


def _report_dir_for_spec(spec):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    report_dir = REPORTS_DIR / "{}_{}".format(str(spec.get("suite_id", "suite")), stamp)
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def run_suite(spec, dry_run=False, max_runs=None, node_counts_override=None, duration_sec_override=None):
    _validate_spec(spec)
    spec_for_run = dict(spec)
    if duration_sec_override is not None:
        spec_for_run["duration_sec"] = int(duration_sec_override)
    cases = _suite_case_rows(spec, max_runs=max_runs, node_counts_override=node_counts_override)
    report_dir = _report_dir_for_spec(spec_for_run)

    if dry_run:
        dry_payload = {
            "report_dir": str(report_dir),
            "cases": cases,
            "phase_id": spec_for_run.get("phase_id"),
            "challenge": spec_for_run.get("challenge"),
            "duration_sec": spec_for_run.get("duration_sec"),
        }
        _write_json(report_dir / "dry_run_manifest.json", dry_payload)
        print(json.dumps(dry_payload, indent=2))
        return report_dir

    base_port = _to_int(spec.get("base_port", 9000), 9000)
    summary_rows = []
    watch_rows = []

    for case in cases:
        number_of_nodes = int(case["nodes"])
        run_index = int(case["run_index"])
        seed = int(case["seed"])

        _stop_nodes()
        run_dir = _start_nodes(number_of_nodes)

        if not _wait_until_ready(base_port, number_of_nodes):
            raise RuntimeError("timed out waiting for {} nodes to become reachable".format(number_of_nodes))

        events_path = run_dir / "paper_events.jsonl"
        active_duration_sec, _ = _run_active_window(spec_for_run, base_port, number_of_nodes, run_index, seed, events_path)
        manifest, summary_row, watch_rows_case, evidence = _collect_evidence(
            spec=spec_for_run,
            run_dir=run_dir,
            events_path=events_path,
            base_port=base_port,
            number_of_nodes=number_of_nodes,
            run_index=run_index,
            seed=seed,
            active_duration_sec=active_duration_sec,
        )
        _write_run_reports(run_dir, manifest, summary_row, watch_rows_case, evidence, events_path)
        summary_rows.append(summary_row)
        watch_rows.extend(watch_rows_case)
        _stop_nodes()

    _write_suite_reports(report_dir, spec, summary_rows, watch_rows)
    return report_dir


def main():
    parser = argparse.ArgumentParser(description="Run phase-based paper evaluation demos")
    parser.add_argument("--spec", required=True, help="Path to a phase spec JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Validate the spec and emit the planned cases without starting nodes")
    parser.add_argument("--max-runs", type=int, help="Optional cap for run_count while testing the suite")
    parser.add_argument("--node-counts", help="Optional comma-separated override for node counts, e.g. 49,64")
    parser.add_argument("--duration-sec", type=int, help="Optional override for a shorter same-machine smoke test duration")
    args = parser.parse_args()

    spec_path = Path(args.spec).resolve()
    spec = _load_spec(spec_path)

    node_counts_override = None
    if args.node_counts:
        node_counts_override = [int(item.strip()) for item in str(args.node_counts).split(",") if len(item.strip()) > 0]

    try:
        report_dir = run_suite(
            spec=spec,
            dry_run=bool(args.dry_run),
            max_runs=args.max_runs,
            node_counts_override=node_counts_override,
            duration_sec_override=args.duration_sec,
        )
    except Exception as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        sys.exit(1)

    print("Report directory: {}".format(str(report_dir)))


if __name__ == "__main__":
    main()
