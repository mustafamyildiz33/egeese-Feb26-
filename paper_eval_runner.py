#!/usr/bin/env python3
"""Phase-based paper evaluation runner for EGESS.

This runner reads a JSON phase specification, executes each requested demo with
an exact active scenario window, and writes Excel-friendly TSV plus Markdown
reports for the whole suite and for each individual run.
"""

import argparse
import csv
import json
import math
import os
import random
import re
import statistics
import subprocess
import sys
import time
from collections import deque
from html import escape
from pathlib import Path
from urllib import request


ROOT_DIR = Path(__file__).resolve().parent
RUNS_DIR = ROOT_DIR / "runs"
REPORTS_DIR = ROOT_DIR / "paper_reports"
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


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
    "detection_speed_sec",
    "first_watch_sec",
    "first_impact_sec",
    "outage_sec",
    "recovery_sec",
    "reset_sec",
    "false_positive_nodes",
    "false_unavailable_refs",
    "settle_accuracy_pct",
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


SUMMARY_BY_NODES_FIELDS = [
    "phase_id",
    "challenge",
    "duration_sec",
    "nodes",
    "runs",
    "avg_total_mb",
    "avg_push_rx_total",
    "avg_tx_fail_total",
    "avg_detection_speed_sec",
    "avg_false_positive_nodes",
    "avg_false_unavailable_refs",
    "avg_settle_accuracy_pct",
]


RUN_OVERVIEW_FIELDS = [
    "phase_id",
    "challenge",
    "nodes",
    "run_index",
    "seed",
    "active_duration_sec",
    "reachable_nodes",
    "total_nodes",
    "events_total",
    "total_mb",
    "detection_speed_sec",
    "tx_fail_total",
    "tx_timeout_total",
    "false_positive_nodes",
    "false_unavailable_refs",
    "status",
]


WATCH_OVERVIEW_FIELDS = [
    "view",
    "watch_port",
    "reachable",
    "protocol_state",
    "accepted_messages",
    "pull_rx",
    "push_rx",
    "pull_tx",
    "push_tx",
    "total_mb",
    "phase",
    "current_missing_count",
    "crash_sim",
    "lie_sensor",
    "flap",
]


NODE_FIELDS = [
    "port",
    "reachable",
    "protocol_state",
    "boundary_kind",
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
    "current_missing_count",
    "crash_sim",
    "lie_sensor",
    "flap",
    "error",
]


HISTORY_FIELDS = [
    "sample_index",
    "sample_sec",
    "sample_label",
    "port",
    "reachable",
    "protocol_state",
    "accepted_messages",
    "pull_rx",
    "push_rx",
    "pull_tx",
    "push_tx",
    "rx_total_bytes",
    "tx_total_bytes",
    "total_bytes",
    "total_mb",
    "phase",
    "current_missing_count",
    "crash_sim",
    "lie_sensor",
    "flap",
    "error",
]


HISTORY_TOTAL_FIELDS = [
    "sample_index",
    "sample_sec",
    "sample_label",
    "reachable_nodes",
    "accepted_messages_total",
    "pull_rx_total",
    "push_rx_total",
    "pull_tx_total",
    "push_tx_total",
    "rx_bytes_total",
    "tx_bytes_total",
    "total_bytes",
    "total_mb",
]


TIMELINE_FIELDS = [
    "milestone",
    "time_sec",
    "status",
    "detail",
]


FIRE_STAGE_FIELDS = [
    "stage",
    "time_window",
    "affected_ports",
    "detail",
]


SUMMARY_CHART_FIELDS = [
    "active_duration_sec",
    "detection_speed_sec",
    "reachable_nodes",
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
    "false_positive_nodes",
    "false_unavailable_refs",
    "settle_accuracy_pct",
]


NODECOUNT_COMPARE_FIELDS = [
    "active_duration_sec",
    "detection_speed_sec",
    "reachable_nodes",
    "events_total",
    "trigger_ops",
    "pull_rx_total",
    "push_rx_total",
    "pull_tx_total",
    "push_tx_total",
    "total_bytes",
    "total_mb",
    "tx_fail_total",
    "tx_timeout_total",
    "false_positive_nodes",
    "false_unavailable_refs",
    "settle_accuracy_pct",
]


WATCH_CHART_FIELDS = [
    "accepted_messages",
    "pull_rx",
    "push_rx",
    "pull_tx",
    "push_tx",
    "total_bytes",
    "total_mb",
]


COMPARISON_FIELDS = [
    "scenario_label",
    "egess_setup",
    "egess_bytes",
    "egess_failures",
    "egess_detection_speed",
    "checkin_setup",
    "checkin_bytes",
    "checkin_failures",
    "checkin_detection_speed",
    "comparison_status",
    "comparison_note",
]


FIELD_LABELS = {
    "active_duration_sec": "Active Time",
    "accepted_messages": "Accepted Msgs",
    "checkin_bytes": "Check-In Bytes",
    "checkin_detection_speed": "Check-In Detection Speed",
    "checkin_failures": "Check-In Failures",
    "checkin_setup": "Check-In Setup",
    "avg_detection_speed_sec": "Avg Detection Speed",
    "avg_false_positive_nodes": "Avg False Positives",
    "avg_false_unavailable_refs": "Avg False Unavailable",
    "avg_push_rx_total": "Avg Push RX",
    "avg_settle_accuracy_pct": "Avg Settle Accuracy",
    "avg_total_mb": "Avg MB",
    "avg_tx_fail_total": "Avg TX Fail",
    "avg": "Average",
    "challenge": "Challenge",
    "comparison_note": "Note",
    "comparison_status": "Compare",
    "coherence_score": "Coherence",
    "crash_sim": "Crash Sim",
    "current_missing_count": "Missing",
    "detail": "Detail",
    "detection_speed_sec": "Detection Speed",
    "direction_label": "Direction",
    "distance_hops": "Distance",
    "duration_sec": "Duration",
    "egess_bytes": "EGESS Bytes",
    "egess_detection_speed": "EGESS Detection Speed",
    "egess_failures": "EGESS Failures",
    "egess_setup": "EGESS Setup",
    "eta_cycles": "ETA",
    "events_total": "Events",
    "false_positive_nodes": "False Positive Nodes",
    "false_unavailable_refs": "False Unavailable Refs",
    "far_watch_port": "Far Port",
    "fault_ops": "Fault Ops",
    "flap": "Flap",
    "front_score": "Front",
    "first_impact_sec": "First Impact",
    "first_watch_sec": "First Watch",
    "impact_score": "Impact",
    "lie_sensor": "Lie Sensor",
    "latest": "Latest",
    "local_watch_port": "Local Port",
    "max": "Max",
    "metric": "Metric",
    "milestone": "Milestone",
    "min": "Min",
    "nodes": "Nodes",
    "phase_id": "Phase",
    "phase_name": "Phase Name",
    "port": "Port",
    "protocol_state": "State",
    "pull_rx": "Pull RX",
    "pull_rx_total": "Pull RX",
    "pull_tx": "Pull TX",
    "pull_tx_total": "Pull TX",
    "push_rx": "Push RX",
    "push_rx_total": "Push RX",
    "push_tx": "Push TX",
    "push_tx_total": "Push TX",
    "reachable_nodes": "Reachable",
    "reachable": "Reachable",
    "run_index": "Run",
    "rx_bytes_total": "RX Bytes",
    "score": "Score",
    "seed": "Seed",
    "sample_index": "Sample",
    "sample_label": "Sample Label",
    "sample_sec": "Sample Time",
    "scenario_label": "Scenario",
    "samples": "Samples",
    "settle_accuracy_pct": "Settle Accuracy",
    "suite_id": "Suite",
    "time_sec": "Time",
    "time_window": "Time Window",
    "total_bytes": "Bytes",
    "total_mb": "MB",
    "total_nodes": "Total Nodes",
    "trigger_ops": "Triggers",
    "tx_conn_error_total": "Conn Err",
    "tx_fail_total": "TX Fail",
    "tx_ok_total": "TX OK",
    "tx_timeout_total": "TX Timeout",
    "tx_total_bytes": "TX Bytes",
    "outage_sec": "Outage",
    "recovery_sec": "Recovery",
    "reset_sec": "Reset",
    "affected_ports": "Affected Ports",
    "stage": "Stage",
    "view": "View",
    "watch_port": "Watch Port",
    "accepted_messages_total": "Accepted Msgs",
    "reachable_nodes": "Reachable",
    "error": "Error",
}


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


def _field_label(field):
    label = FIELD_LABELS.get(str(field), "")
    if label:
        return label
    return str(field).replace("_", " ").title()


def _maybe_float(value):
    if isinstance(value, bool) or value in ("", None):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _maybe_int(value):
    number = _maybe_float(value)
    if number is None:
        return None
    if float(number).is_integer():
        return int(number)
    return None


def _boolish(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return None
    text = str(value).strip().lower()
    if text in ("true", "yes"):
        return True
    if text in ("false", "no"):
        return False
    return None


def _format_display_value(field, value):
    if value in ("", None):
        return ""

    truthy = _boolish(value)
    if truthy is not None:
        return "Yes" if truthy else "No"

    number_int = _maybe_int(value)
    number_float = _maybe_float(value)

    if field in (
        "duration_sec",
        "active_duration_sec",
        "detection_speed_sec",
        "first_watch_sec",
        "first_impact_sec",
        "outage_sec",
        "recovery_sec",
        "reset_sec",
        "time_sec",
    ) and number_float is not None:
        return "{:.3f}s".format(float(number_float))
    if field.endswith("_pct") and number_float is not None:
        return "{:.1f}%".format(float(number_float))
    if field.endswith("_mb") and number_float is not None:
        return "{:.3f} MB".format(float(number_float))
    if field in ("rx_bytes_total", "tx_bytes_total", "total_bytes") and number_int is not None:
        return "{:,}".format(int(number_int))
    if field in (
        "accepted_messages",
        "events_total",
        "fault_ops",
        "trigger_ops",
        "pull_rx",
        "push_rx",
        "pull_tx",
        "push_tx",
        "pull_rx_total",
        "push_rx_total",
        "pull_tx_total",
        "push_tx_total",
        "reachable_nodes",
        "total_nodes",
        "run_index",
        "seed",
        "nodes",
        "watch_port",
        "local_watch_port",
        "far_watch_port",
        "tx_ok_total",
        "tx_fail_total",
        "tx_timeout_total",
        "tx_conn_error_total",
        "current_missing_count",
        "false_positive_nodes",
        "false_unavailable_refs",
        "runs",
    ) and number_int is not None:
        return "{:,}".format(int(number_int))
    if field in (
        "score",
        "front_score",
        "impact_score",
        "arrest_score",
        "coherence_score",
        "avg_total_mb",
        "avg_push_rx_total",
        "avg_tx_fail_total",
        "distance_hops",
        "eta_cycles",
    ) and number_float is not None:
        return "{:.3f}".format(float(number_float))

    return str(value)


def _value_is_positive(field, value):
    number = _maybe_float(value)
    if number is None:
        return False
    if field in ("reachable_nodes", "total_nodes", "pull_rx", "push_rx", "pull_tx", "push_tx", "events_total", "accepted_messages"):
        return number > 0
    return number > 0


def _cell_class(field, value):
    classes = ["col-{}".format(str(field).replace("_", "-"))]
    number = _maybe_float(value)
    if field in (
        "tx_fail_total",
        "tx_timeout_total",
        "tx_conn_error_total",
        "current_missing_count",
        "avg_tx_fail_total",
        "false_positive_nodes",
        "false_unavailable_refs",
        "avg_false_positive_nodes",
        "avg_false_unavailable_refs",
    ):
        classes.append("metric-bad" if number and number > 0 else "metric-good")
    elif field in ("settle_accuracy_pct", "avg_settle_accuracy_pct"):
        classes.append("metric-good")
    elif field in ("egess_failures", "checkin_failures"):
        classes.append("metric-bad")
    elif field in ("total_mb", "avg_total_mb", "rx_bytes_total", "tx_bytes_total", "total_bytes"):
        classes.append("metric-accent")
    elif field in (
        "egess_bytes",
        "checkin_bytes",
        "egess_detection_speed",
        "checkin_detection_speed",
        "detection_speed_sec",
        "avg_detection_speed_sec",
        "first_watch_sec",
        "first_impact_sec",
        "outage_sec",
        "recovery_sec",
        "reset_sec",
    ):
        classes.append("metric-accent")
    elif field in ("events_total", "accepted_messages", "pull_rx", "push_rx", "pull_tx", "push_tx", "pull_rx_total", "push_rx_total", "pull_tx_total", "push_tx_total"):
        if _value_is_positive(field, value):
            classes.append("metric-ink")
    return " ".join(classes)


def _badge_class(field, value):
    text = str(value).strip()
    lower_text = text.lower()
    truthy = _boolish(value)

    if field == "status":
        if lower_text == "ok":
            return "pill-good"
        if lower_text in ("warn", "warning"):
            return "pill-warn"
        return "pill-bad"
    if field == "comparison_status":
        if lower_text == "fair":
            return "pill-good"
        if lower_text == "mismatch":
            return "pill-warn"
        return "pill-bad"
    if field == "view":
        if text.upper() == "LOCAL":
            return "pill-local"
        if text.upper() == "FAR":
            return "pill-far"
    if field in ("protocol_state", "phase"):
        return "pill-soft"
    if field == "reachable" and truthy is not None:
        return "pill-good" if truthy else "pill-bad"
    if field in ("crash_sim", "lie_sensor", "flap") and truthy is not None:
        return "pill-bad" if truthy else "pill-off"
    return ""


def _row_class(row):
    classes = []
    if str(row.get("status", "")).strip().lower() == "ok":
        classes.append("row-ok")
    elif str(row.get("status", "")).strip():
        classes.append("row-alert")
    if str(row.get("comparison_status", "")).strip().lower() == "fair":
        classes.append("row-ok")
    elif str(row.get("comparison_status", "")).strip():
        classes.append("row-alert")
    if str(row.get("view", "")).strip().upper() == "LOCAL":
        classes.append("row-local")
    elif str(row.get("view", "")).strip().upper() == "FAR":
        classes.append("row-far")
    return " ".join(classes)


def _render_table_html(title, rows, fields, subtitle=""):
    head = []
    for field in fields:
        head.append("<th>{}</th>".format(escape(_field_label(field))))

    body = []
    if rows:
        for row in rows:
            cells = []
            for field in fields:
                display = escape(_format_display_value(field, row.get(field, "")))
                badge_class = _badge_class(field, row.get(field, ""))
                if badge_class:
                    display = '<span class="badge {}">{}</span>'.format(badge_class, display)
                cells.append('<td class="{}">{}</td>'.format(_cell_class(field, row.get(field, "")), display))
            body.append('<tr class="{}">{}</tr>'.format(_row_class(row), "".join(cells)))
    else:
        body.append('<tr><td colspan="{}" class="empty">No rows recorded.</td></tr>'.format(len(fields)))

    subtitle_html = ""
    if subtitle:
        subtitle_html = '<p class="section-note">{}</p>'.format(escape(subtitle))

    return """<section class="panel">
<div class="panel-head">
  <h2>{title}</h2>
  {subtitle}
</div>
<div class="table-wrap">
  <table>
    <thead><tr>{head}</tr></thead>
    <tbody>{body}</tbody>
  </table>
</div>
</section>""".format(
        title=escape(title),
        subtitle=subtitle_html,
        head="".join(head),
        body="".join(body),
    )


def _render_cards_html(cards):
    chunks = []
    for card in cards:
        tone = str(card.get("tone", "neutral")).strip()
        chunks.append(
            """<div class="stat-card {tone}">
  <div class="stat-label">{label}</div>
  <div class="stat-value">{value}</div>
  <div class="stat-note">{note}</div>
</div>""".format(
                tone=escape(tone),
                label=escape(str(card.get("label", ""))),
                value=escape(str(card.get("value", ""))),
                note=escape(str(card.get("note", ""))),
            )
        )
    return '<section class="card-grid">{}</section>'.format("".join(chunks))


def _render_links_html(title, links):
    items = []
    for href, label in links:
        items.append('<li><a href="{href}">{label}</a></li>'.format(href=escape(str(href)), label=escape(str(label))))
    return """<section class="panel">
<div class="panel-head">
  <h2>{}</h2>
</div>
<ul class="link-list">{}</ul>
</section>""".format(escape(title), "".join(items))


def _render_run_deep_dive_html(report_dir, summary_rows):
    if not summary_rows:
        return """<section class="panel">
<div class="panel-head">
  <h2>Run Deep Dives</h2>
  <p class="section-note">Node Spotlight lives on the per-run dashboard, but no runs are available yet.</p>
</div>
</section>"""

    cards = []
    for row in sorted(summary_rows, key=lambda item: (int(item.get("nodes", 0)), int(item.get("run_index", 0)))):
        run_path = ROOT_DIR / str(row.get("run_dir", "")).strip() / "paper_summary.html"
        href = os.path.relpath(run_path, start=report_dir)
        status = _format_display_value("status", row.get("status", ""))
        badge_class = _badge_class("status", row.get("status", "")) or "pill-soft"
        cards.append(
            """<article class="run-link-card">
  <div class="run-link-top">
    <div>
      <div class="run-link-title">Run {run_index} · N{nodes}</div>
      <div class="run-link-meta">Seed {seed} · {challenge}</div>
    </div>
    <span class="badge {badge_class}">{status}</span>
  </div>
  <div class="run-link-stats">
    <span>{active_time}</span>
    <span>{traffic}</span>
    <span>{failures} TX fail</span>
  </div>
  <a class="run-link-action" href="{href}">Open Node Spotlight</a>
</article>""".format(
                run_index=escape(_format_display_value("run_index", row.get("run_index", ""))),
                nodes=escape(_format_display_value("nodes", row.get("nodes", ""))),
                seed=escape(_format_display_value("seed", row.get("seed", ""))),
                challenge=escape(_format_display_value("challenge", row.get("challenge", ""))),
                badge_class=escape(badge_class),
                status=escape(status),
                active_time=escape(_format_display_value("active_duration_sec", row.get("active_duration_sec", ""))),
                traffic=escape(_format_display_value("total_mb", row.get("total_mb", ""))),
                failures=escape(_format_display_value("tx_fail_total", row.get("tx_fail_total", ""))),
                href=escape(href),
            )
        )

    return """<section class="panel">
<div class="panel-head">
  <h2>Run Deep Dives</h2>
  <p class="section-note">Open any run below to use Node Spotlight, inspect a specific port, and see that node's counters and history.</p>
</div>
<div class="run-link-grid">{}</div>
</section>""".format("".join(cards))


def _html_page(title, subtitle, cards_html, sections_html, script_html=""):
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #f5f7fb;
      --panel: rgba(255, 255, 255, 0.92);
      --panel-strong: #ffffff;
      --ink: #18212f;
      --muted: #5d6b82;
      --line: #d9e1ef;
      --blue: #2474e5;
      --blue-soft: #e8f1ff;
      --teal: #118a7e;
      --teal-soft: #e6fbf5;
      --gold: #c58f10;
      --gold-soft: #fff5d8;
      --red: #c73a3a;
      --red-soft: #ffe6e6;
      --purple-soft: #f1ebff;
      --orange-soft: #fff0e4;
      --shadow: 0 18px 48px rgba(22, 37, 66, 0.10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(36, 116, 229, 0.12), transparent 28%),
        radial-gradient(circle at top right, rgba(17, 138, 126, 0.12), transparent 30%),
        linear-gradient(180deg, #fbfcff 0%, var(--bg) 100%);
    }}
    .page {{
      max-width: 1380px;
      margin: 0 auto;
      padding: 28px 24px 48px;
    }}
    .hero {{
      background: linear-gradient(135deg, rgba(36, 116, 229, 0.98), rgba(17, 138, 126, 0.92));
      color: #ffffff;
      border-radius: 24px;
      padding: 24px 28px;
      box-shadow: var(--shadow);
      margin-bottom: 22px;
    }}
    .hero h1 {{
      margin: 0 0 6px;
      font-size: 2rem;
      line-height: 1.1;
    }}
    .hero p {{
      margin: 0;
      color: rgba(255, 255, 255, 0.90);
      font-size: 1rem;
    }}
    .card-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin-bottom: 20px;
    }}
    .stat-card {{
      background: var(--panel-strong);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px 18px;
      box-shadow: var(--shadow);
    }}
    .stat-card.good {{ background: linear-gradient(180deg, var(--panel-strong), #f2fffb); }}
    .stat-card.warn {{ background: linear-gradient(180deg, var(--panel-strong), #fffaf0); }}
    .stat-card.bad {{ background: linear-gradient(180deg, var(--panel-strong), #fff4f4); }}
    .stat-card.accent {{ background: linear-gradient(180deg, var(--panel-strong), #f3f7ff); }}
    .stat-label {{
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 6px;
    }}
    .stat-value {{
      font-size: 1.55rem;
      font-weight: 700;
      margin-bottom: 4px;
    }}
    .stat-note {{
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid rgba(217, 225, 239, 0.9);
      border-radius: 22px;
      padding: 18px;
      box-shadow: var(--shadow);
      margin-bottom: 18px;
      backdrop-filter: blur(6px);
    }}
    .panel-head {{
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }}
    .panel h2 {{
      margin: 0;
      font-size: 1.1rem;
    }}
    .section-note {{
      margin: 0;
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .table-wrap {{
      overflow-x: auto;
      border-radius: 16px;
      border: 1px solid var(--line);
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      min-width: 840px;
      background: #ffffff;
    }}
    th, td {{
      padding: 11px 12px;
      border-bottom: 1px solid #e8edf6;
      text-align: left;
      white-space: nowrap;
      vertical-align: top;
    }}
    th {{
      position: sticky;
      top: 0;
      z-index: 1;
      background: #eef4ff;
      color: #294067;
      font-size: 0.84rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    tbody tr:nth-child(even) {{
      background: rgba(245, 248, 253, 0.75);
    }}
    .row-local {{
      background: linear-gradient(90deg, rgba(255, 240, 228, 0.85), rgba(255, 255, 255, 0));
    }}
    .row-far {{
      background: linear-gradient(90deg, rgba(232, 241, 255, 0.85), rgba(255, 255, 255, 0));
    }}
    .badge {{
      display: inline-block;
      border-radius: 999px;
      padding: 4px 10px;
      font-weight: 700;
      font-size: 0.84rem;
    }}
    .pill-good {{ background: var(--teal-soft); color: #10695f; }}
    .pill-warn {{ background: var(--gold-soft); color: #7a5905; }}
    .pill-bad {{ background: var(--red-soft); color: #922d2d; }}
    .pill-local {{ background: var(--orange-soft); color: #8b4c12; }}
    .pill-far {{ background: var(--blue-soft); color: #1a57b2; }}
    .pill-soft {{ background: var(--purple-soft); color: #5c3f9f; }}
    .pill-off {{ background: #eef2f8; color: #5d6b82; }}
    .metric-accent {{ color: #125bb8; font-weight: 700; }}
    .metric-bad {{ color: #b03232; font-weight: 700; }}
    .metric-good {{ color: #0f7a5b; font-weight: 700; }}
    .metric-ink {{ font-weight: 650; }}
    .chart-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
    }}
    .timeline-strip {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      position: relative;
    }}
    .timeline-item {{
      position: relative;
      padding-left: 16px;
    }}
    .timeline-item::before {{
      content: "";
      position: absolute;
      left: 6px;
      top: 18px;
      bottom: -12px;
      width: 2px;
      background: linear-gradient(180deg, rgba(36, 116, 229, 0.22), rgba(17, 138, 126, 0.18));
    }}
    .timeline-item:last-child::before {{
      bottom: 18px;
    }}
    .timeline-dot {{
      position: absolute;
      left: 0;
      top: 18px;
      width: 14px;
      height: 14px;
      border-radius: 999px;
      background: linear-gradient(135deg, #2474e5, #118a7e);
      box-shadow: 0 0 0 4px rgba(36, 116, 229, 0.10);
    }}
    .timeline-card {{
      background: linear-gradient(180deg, #ffffff, #f8fbff);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px 14px 14px 18px;
      min-height: 138px;
    }}
    .timeline-top {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 8px;
    }}
    .timeline-top h3 {{
      margin: 0;
      font-size: 0.98rem;
    }}
    .timeline-time {{
      font-size: 1.14rem;
      font-weight: 800;
      margin-bottom: 6px;
    }}
    .timeline-detail {{
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.45;
    }}
    .chart-card {{
      background: linear-gradient(180deg, #ffffff, #f9fbff);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px;
    }}
    .chart-title {{
      font-weight: 700;
      margin-bottom: 4px;
    }}
    .chart-stats,
    .chart-footer,
    .chart-empty {{
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .chart-annotations {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
      margin-bottom: 8px;
    }}
    .chart-pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 0.84rem;
      font-weight: 700;
      background: #eef2f8;
      color: #4a5870;
    }}
    .chart-pill.good {{
      background: var(--teal-soft);
      color: #10695f;
    }}
    .chart-pill.bad {{
      background: var(--red-soft);
      color: #922d2d;
    }}
    .chart-pill.soft {{
      background: #eef2f8;
      color: #5d6b82;
    }}
    .chart-footer {{
      margin-top: 8px;
    }}
    .chart-detail {{
      margin-top: 10px;
      padding: 10px 12px;
      border-radius: 12px;
      background: rgba(239, 244, 255, 0.85);
      border: 1px solid #dbe5f6;
      color: #38506f;
      font-size: 0.9rem;
      line-height: 1.4;
    }}
    .chart-detail strong {{
      color: var(--ink);
    }}
    .metric-chart {{
      width: 100%;
      height: auto;
      margin-top: 8px;
      display: block;
    }}
    .chart-axis {{
      stroke: #cfd8e8;
      stroke-width: 1;
    }}
    .chart-point {{
      cursor: pointer;
      transition: r 0.15s ease, transform 0.15s ease;
      transform-origin: center;
    }}
    .chart-point:hover,
    .chart-point:focus,
    .chart-point.is-active {{
      r: 4.8;
      outline: none;
    }}
    .guide-grid,
    .control-grid,
    .spotlight-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
    }}
    .guide-card,
    .control-card,
    .spotlight-card {{
      background: linear-gradient(180deg, #ffffff, #f8fbff);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
    }}
    .guide-card h3,
    .control-card h3,
    .spotlight-card h3 {{
      margin: 0 0 8px;
      font-size: 1rem;
    }}
    .guide-card p,
    .control-card p,
    .spotlight-card p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.45;
    }}
    .guide-table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 12px;
    }}
    .guide-table th,
    .guide-table td {{
      padding: 10px 12px;
      border-bottom: 1px solid #e8edf6;
      text-align: left;
      vertical-align: top;
    }}
    .guide-table th {{
      background: #eef4ff;
      color: #294067;
      font-size: 0.84rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .guide-list-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 14px;
    }}
    .guide-list-card {{
      background: linear-gradient(180deg, #ffffff, #f8fbff);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
    }}
    .guide-list-card h3 {{
      margin: 0 0 10px;
      font-size: 1rem;
    }}
    .guide-list {{
      margin: 0;
      padding-left: 18px;
      display: grid;
      gap: 8px;
      color: var(--muted);
      line-height: 1.45;
    }}
    .guide-list strong {{
      color: var(--ink);
    }}
    .control-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 8px;
      align-items: end;
    }}
    .control-field {{
      display: flex;
      flex-direction: column;
      gap: 6px;
      min-width: 170px;
      flex: 1 1 190px;
    }}
    .control-field label {{
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
      font-weight: 700;
    }}
    .control-field input,
    .control-field select {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px 12px;
      font: inherit;
      background: #ffffff;
      color: var(--ink);
      box-shadow: inset 0 1px 2px rgba(24, 33, 47, 0.04);
    }}
    .micro-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 10px;
      margin-top: 12px;
    }}
    .micro-card {{
      background: linear-gradient(180deg, #f8fbff, #ffffff);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px;
    }}
    .micro-label {{
      color: var(--muted);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 4px;
    }}
    .micro-value {{
      font-weight: 700;
      font-size: 1.12rem;
    }}
    .micro-note {{
      color: var(--muted);
      font-size: 0.88rem;
      margin-top: 4px;
    }}
    .spotlight-banner {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 14px;
      padding: 14px 16px;
      border-radius: 18px;
      background: linear-gradient(135deg, rgba(36, 116, 229, 0.12), rgba(17, 138, 126, 0.10));
      border: 1px solid rgba(36, 116, 229, 0.16);
      margin-top: 8px;
      flex-wrap: wrap;
    }}
    .spotlight-banner-label {{
      color: var(--muted);
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 4px;
    }}
    .spotlight-banner-title {{
      font-size: 1.3rem;
      font-weight: 800;
      margin-bottom: 4px;
    }}
    .spotlight-banner-subtitle {{
      color: var(--muted);
      font-size: 0.94rem;
    }}
    .spotlight-chip-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}
    .jump-chip {{
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 999px;
      padding: 8px 12px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }}
    .jump-chip:hover {{
      background: #f3f7ff;
    }}
    .jump-chip:disabled {{
      opacity: 0.45;
      cursor: not-allowed;
    }}
    .spotlight-log {{
      list-style: none;
      padding: 0;
      margin: 12px 0 0;
      display: grid;
      gap: 8px;
    }}
    .spotlight-log li {{
      background: rgba(239, 244, 255, 0.9);
      border: 1px solid #dbe5f6;
      border-radius: 12px;
      padding: 8px 10px;
      font-size: 0.92rem;
      line-height: 1.4;
    }}
    .spotlight-log-tail {{
      margin: 12px 0 0;
      min-height: 220px;
      max-height: 360px;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
      background: #0f172a;
      color: #dbeafe;
      border-radius: 14px;
      border: 1px solid rgba(148, 163, 184, 0.24);
      padding: 12px 14px;
      font: 0.84rem/1.45 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
    }}
    .accent-note {{
      color: #1f63c6;
      font-weight: 700;
    }}
    .empty {{
      text-align: center;
      color: var(--muted);
      padding: 18px;
    }}
    .link-list {{
      margin: 0;
      padding-left: 18px;
    }}
    .link-list li {{
      margin: 8px 0;
    }}
    .link-list a {{
      color: var(--blue);
      text-decoration: none;
      font-weight: 600;
    }}
    .link-list a:hover {{
      text-decoration: underline;
    }}
    .run-link-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
    }}
    .run-link-card {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(247,250,255,0.98));
      box-shadow: 0 10px 24px rgba(24, 33, 47, 0.06);
    }}
    .run-link-top {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .run-link-title {{
      font-size: 1.05rem;
      font-weight: 700;
      margin-bottom: 4px;
    }}
    .run-link-meta {{
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .run-link-stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 14px;
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .run-link-stats span {{
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(36, 116, 229, 0.08);
    }}
    .run-link-action {{
      display: inline-block;
      padding: 10px 14px;
      border-radius: 12px;
      background: linear-gradient(135deg, #2474e5, #118a7e);
      color: white;
      text-decoration: none;
      font-weight: 700;
    }}
    .run-link-action:hover {{
      opacity: 0.92;
    }}
    .spotlight-row-selectable {{
      cursor: pointer;
    }}
    .spotlight-row-selectable:hover {{
      background: rgba(36, 116, 229, 0.08) !important;
    }}
    .spotlight-row-selectable:focus {{
      outline: none;
      box-shadow: inset 0 0 0 2px rgba(36, 116, 229, 0.42);
    }}
    .row-selected {{
      box-shadow: inset 0 0 0 2px rgba(17, 138, 126, 0.42);
      background: rgba(17, 138, 126, 0.08) !important;
    }}
    .scenario-tab-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 14px;
    }}
    .scenario-tab {{
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #ffffff;
      color: var(--muted);
      padding: 8px 14px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 4px 14px rgba(24, 33, 47, 0.05);
    }}
    .scenario-tab.active {{
      background: linear-gradient(135deg, #2474e5, #118a7e);
      color: #ffffff;
      border-color: transparent;
    }}
    .nodecount-panel {{
      display: none;
    }}
    .nodecount-panel.active {{
      display: block;
    }}
    .delta-chip {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 4px 9px;
      font-weight: 700;
      font-size: 0.84rem;
      margin-right: 6px;
      white-space: nowrap;
    }}
    .delta-up {{
      background: rgba(180, 83, 9, 0.12);
      color: #9a4f08;
    }}
    .delta-down {{
      background: rgba(15, 118, 110, 0.12);
      color: #0f766e;
    }}
    .delta-flat {{
      background: #eef2f8;
      color: #617086;
    }}
    .delta-subnote {{
      color: var(--muted);
      font-size: 0.84rem;
      white-space: nowrap;
    }}
    .compare-current {{
      background: rgba(36, 116, 229, 0.08) !important;
      box-shadow: inset 0 0 0 1px rgba(36, 116, 229, 0.16);
    }}
    details {{
      margin-top: 14px;
    }}
    summary {{
      cursor: pointer;
      color: var(--blue);
      font-weight: 700;
    }}
    @media (max-width: 720px) {{
      .page {{ padding: 16px 14px 36px; }}
      .hero {{ padding: 18px 18px; border-radius: 18px; }}
      .hero h1 {{ font-size: 1.55rem; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <h1>{title}</h1>
      <p>{subtitle}</p>
    </section>
    {cards}
    {sections}
  </main>
  <script>
    (() => {{
      const cards = Array.from(document.querySelectorAll('.interactive-chart-card'));
      cards.forEach((card) => {{
        const detail = card.querySelector('.chart-detail');
        const points = Array.from(card.querySelectorAll('.chart-point'));
        if (!detail || !points.length) return;

        const updateDetail = (point) => {{
          points.forEach((item) => item.classList.toggle('is-active', item === point));
          const label = point.getAttribute('data-label') || '';
          const value = point.getAttribute('data-value-display') || point.getAttribute('data-value') || '';
          const delta = point.getAttribute('data-delta-display') || 'n/a';
          detail.innerHTML = `<strong>${{label}}</strong> · value ${{value}} · delta ${{delta}}`;
        }};

        points.forEach((point) => {{
          point.addEventListener('mouseenter', () => updateDetail(point));
          point.addEventListener('focus', () => updateDetail(point));
          point.addEventListener('click', () => updateDetail(point));
        }});

        updateDetail(points[points.length - 1]);
      }});
    }})();
  </script>
  {script_html}
</body>
</html>""".format(
        title=escape(str(title)),
        subtitle=escape(str(subtitle)),
        cards=cards_html,
        sections=sections_html,
        script_html=script_html,
    )


def _write_text(path, content):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def _strip_ansi(text):
    return ANSI_ESCAPE_RE.sub("", str(text or ""))


def _tail_text_lines(path, max_lines=40):
    file_path = Path(path)
    if not file_path.exists():
        return []
    out = deque(maxlen=max_lines)
    with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = _strip_ansi(raw_line.rstrip("\n")).strip()
            if line:
                out.append(line)
    return list(out)


def _node_log_tails(run_dir, ports, max_lines=40):
    out = {}
    for port in sorted({_to_int(port, -1) for port in ports if _to_int(port, -1) >= 0}):
        out[str(port)] = _tail_text_lines(Path(run_dir) / "node_{}.log".format(int(port)), max_lines=max_lines)
    return out


def _load_jsonl(path):
    rows = []
    file_path = Path(path)
    if not file_path.exists():
        return rows
    with open(file_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _resolved_protocol_state_from_state(state):
    state = state if isinstance(state, dict) else {}
    protocol_state = str(state.get("protocol_state", "")).strip().upper()
    if protocol_state:
        return protocol_state
    if bool(state.get("DESTROYED", False)):
        return "DESTROYED"
    if bool(state.get("SURVEYING", False)):
        return "SURVEYING"
    if bool(state.get("ALARMED", False)):
        return "ALARMED"
    if bool(state.get("ON_FIRE", False)):
        return "ON_FIRE"
    if bool(state.get("NORMAL", False)):
        return "NORMAL"
    return ""


def _resolved_phase_from_state(state):
    state = state if isinstance(state, dict) else {}
    layer2 = state.get("layer2_confirmation", {}) if isinstance(state.get("layer2_confirmation"), dict) else {}
    phase = str(layer2.get("phase", "")).strip().upper()
    if phase:
        return phase
    return _resolved_protocol_state_from_state(state)


def _is_normalish_label(text):
    return str(text or "").strip().upper() in ("", "NORMAL", "STABLE", "CLEAR")


def _false_unavailable_refs_from_state(state):
    state = state if isinstance(state, dict) else {}
    refs = set()

    current_missing = state.get("current_missing_neighbors", [])
    if isinstance(current_missing, list):
        refs.update(str(item) for item in current_missing if str(item).strip())

    persistent_missing = state.get("persistent_missing_neighbors", [])
    if isinstance(persistent_missing, list):
        refs.update(str(item) for item in persistent_missing if str(item).strip())

    new_missing = state.get("new_missing_neighbors", [])
    if isinstance(new_missing, list):
        refs.update(str(item) for item in new_missing if str(item).strip())

    surveying_targets = state.get("surveying_targets", {})
    if isinstance(surveying_targets, dict):
        refs.update(str(key) for key in surveying_targets.keys() if str(key).strip())

    neighbor_states = state.get("neighbor_states", {})
    if isinstance(neighbor_states, dict):
        for key, value in neighbor_states.items():
            if not str(key).strip():
                continue
            if isinstance(value, dict):
                unavailable = (
                    bool(value.get("DESTROYED", False))
                    or bool(value.get("UNAVAILABLE", False))
                    or value.get("available") is False
                )
                if unavailable:
                    refs.add(str(key))

    return len(refs)


def _false_positive_flag_from_state(state):
    protocol_state = _resolved_protocol_state_from_state(state)
    phase = _resolved_phase_from_state(state)
    if not _is_normalish_label(protocol_state):
        return 1
    if not _is_normalish_label(phase):
        return 1
    if _false_unavailable_refs_from_state(state) > 0:
        return 1
    return 0


def _history_row_has_hazard_signal(row):
    state = str(row.get("protocol_state", "")).strip().upper()
    phase = str(row.get("phase", "")).strip().upper()
    if not _is_normalish_label(state):
        return True
    if not _is_normalish_label(phase):
        return True
    if _to_int(row.get("current_missing_count", 0), 0) > 0:
        return True
    for field in ("crash_sim", "lie_sensor", "flap"):
        if _boolish(row.get(field, "")):
            return True
    return False


def _history_row_is_impact(row):
    return _history_row_has_hazard_signal(row)


def _event_at_sec(row):
    data = row.get("data", {}) if isinstance(row, dict) else {}
    if isinstance(data, dict):
        number = _maybe_float(data.get("at_sec"))
        if number is not None:
            return float(number)
    return None


def _event_label(row):
    data = row.get("data", {}) if isinstance(row, dict) else {}
    if isinstance(data, dict):
        return str(data.get("label", "")).strip()
    return ""


def _event_port(row):
    data = row.get("data", {}) if isinstance(row, dict) else {}
    if isinstance(data, dict):
        return _to_int(data.get("port", 0), 0)
    return 0


def _first_matching_event(events_rows, predicate):
    for row in sorted(events_rows or [], key=lambda item: (_event_at_sec(item) if _event_at_sec(item) is not None else 1e9, str(item.get("ts", "")))):
        if predicate(row):
            return row
    return None


def _history_rows_for_port(history_rows, port):
    out = []
    for row in history_rows or []:
        if _to_int(row.get("port", -1), -1) != int(port):
            continue
        if str(row.get("error", "")).strip():
            continue
        out.append(row)
    out.sort(key=lambda row: (_to_int(row.get("sample_index", 0), 0), _to_float(row.get("sample_sec", 0.0), 0.0)))
    return out


def _first_matching_history_row(history_rows, port, predicate):
    for row in _history_rows_for_port(history_rows, port):
        if predicate(row):
            return row
    return None


def _timeline_row(milestone, time_sec=None, status="", detail=""):
    return {
        "milestone": str(milestone),
        "time_sec": "" if time_sec is None else round(float(time_sec), 3),
        "status": str(status),
        "detail": str(detail),
    }


def _derive_run_timeline(spec, manifest, history_rows, events_rows):
    watch_ports = manifest.get("watch_ports", {}) if isinstance(manifest, dict) else {}
    local_port = _to_int(watch_ports.get("LOCAL", 0), 0)
    scenario_kind = str(spec.get("scenario", {}).get("kind", "")).strip().lower()

    first_watch_row = _first_matching_history_row(history_rows, local_port, _history_row_has_hazard_signal) if local_port > 0 else None
    first_impact_row = _first_matching_history_row(history_rows, local_port, _history_row_is_impact) if local_port > 0 else None

    def has_label_prefix(prefix):
        return lambda row: _event_label(row).startswith(prefix)

    def has_label_text(*needles):
        lowered = [str(needle).lower() for needle in needles]
        return lambda row: any(needle in _event_label(row).lower() for needle in lowered)

    ignition_event = None
    if scenario_kind == "firebomb":
        ignition_event = _first_matching_event(events_rows, has_label_prefix("fire_front_step_1"))
    elif scenario_kind == "tornado_sweep":
        ignition_event = _first_matching_event(events_rows, has_label_prefix("tornado_step_1"))
    elif scenario_kind == "ghost_outage_noise":
        ignition_event = _first_matching_event(events_rows, has_label_text("ghost_outage_on", "lie_sensor_on", "flap_on"))
    elif scenario_kind == "baseline":
        ignition_event = _first_matching_event(events_rows, lambda row: str(row.get("kind", "")) == "stage" and str((row.get("data") or {}).get("name", "")) == "active_window_start")

    outage_event = _first_matching_event(
        events_rows,
        lambda row: (
            str(row.get("kind", "")) == "fault"
            and (
                str((row.get("data") or {}).get("fault", "")).strip().lower() == "crash_sim"
                and bool((row.get("data") or {}).get("enable", False))
                or "impact" in _event_label(row).lower()
                or _event_label(row).lower().startswith("tornado_step_")
            )
        )
        or (
            str(row.get("kind", "")) == "state"
            and str((row.get("data") or {}).get("sensor_state", "")).strip().upper() in ("DESTROYED",)
        ),
    )
    recovery_event = _first_matching_event(
        events_rows,
        lambda row: "recover" in _event_label(row).lower()
        or (
            str(row.get("kind", "")) == "state"
            and str((row.get("data") or {}).get("sensor_state", "")).strip().upper() in ("RECOVERING", "SURVEYING")
        ),
    )
    reset_event = _first_matching_event(
        events_rows,
        lambda row: "reset" in _event_label(row).lower()
        or (
            str(row.get("kind", "")) == "state"
            and str((row.get("data") or {}).get("sensor_state", "")).strip().upper() == "NORMAL"
        ),
    )

    first_watch_sec = _to_float(first_watch_row.get("sample_sec", 0.0), 0.0) if first_watch_row else None
    first_impact_sec = _to_float(first_impact_row.get("sample_sec", 0.0), 0.0) if first_impact_row else None
    ignition_sec = _event_at_sec(ignition_event)
    outage_sec = _event_at_sec(outage_event)
    recovery_sec = _event_at_sec(recovery_event)
    reset_sec = _event_at_sec(reset_event)

    timeline_rows = [
        _timeline_row("Ignition", ignition_sec, "Observed" if ignition_sec is not None else "n/a", _event_label(ignition_event) or "No ignition event logged"),
        _timeline_row(
            "First Watch",
            first_watch_sec,
            "Observed" if first_watch_sec is not None else "n/a",
            "LOCAL watch port {} first showed a hazard signal".format(local_port) if first_watch_sec is not None and local_port > 0 else "LOCAL watch did not show a hazard signal",
        ),
        _timeline_row(
            "First Impact",
            first_impact_sec,
            "Observed" if first_impact_sec is not None else "n/a",
            "First local non-normal phase or state sample" if first_impact_sec is not None else "No impact sample recorded",
        ),
        _timeline_row("Outage", outage_sec, "Observed" if outage_sec is not None else "n/a", _event_label(outage_event) or "No outage event logged"),
        _timeline_row("Recovery", recovery_sec, "Observed" if recovery_sec is not None else "n/a", _event_label(recovery_event) or "No recovery event logged"),
        _timeline_row("Reset", reset_sec, "Observed" if reset_sec is not None else "n/a", _event_label(reset_event) or "No reset event logged"),
    ]
    metrics = {
        "detection_speed_sec": first_watch_sec,
        "first_watch_sec": first_watch_sec,
        "first_impact_sec": first_impact_sec,
        "outage_sec": outage_sec,
        "recovery_sec": recovery_sec,
        "reset_sec": reset_sec,
    }
    return timeline_rows, metrics


def _fire_stage_rows(events_rows):
    labels = {
        "Ignition": ("fire_front_step_1",),
        "Front Expansion": tuple("fire_front_step_{}".format(idx) for idx in range(1, 32)),
        "Bomb Core": ("bomb_core_impact", "bomb_core_recover"),
        "Recovery": tuple("fire_recover_step_{}".format(idx) for idx in range(1, 32)) + ("fire_reset",),
    }
    out = []
    rows = events_rows or []
    for stage, label_prefixes in labels.items():
        matching = [row for row in rows if _event_label(row) and any(_event_label(row).startswith(prefix) for prefix in label_prefixes)]
        if not matching:
            continue
        times = [value for value in (_event_at_sec(row) for row in matching) if value is not None]
        ports = sorted({str(_event_port(row)) for row in matching if _event_port(row) > 0})
        first_label = _event_label(matching[0])
        if times:
            window = "{:.3f}s".format(times[0]) if len(set(times)) == 1 else "{:.3f}s to {:.3f}s".format(min(times), max(times))
        else:
            window = "n/a"
        out.append(
            {
                "stage": stage,
                "time_window": window,
                "affected_ports": ", ".join(ports[:10]) + (" ..." if len(ports) > 10 else ""),
                "detail": first_label,
            }
        )
    return out


def _node_row_from_state(port, reachable, state=None, counters=None, error=""):
    state = state if isinstance(state, dict) else {}
    counters = counters if isinstance(counters, dict) else {}
    layer2 = state.get("layer2_confirmation", {}) if isinstance(state.get("layer2_confirmation"), dict) else {}
    faults = state.get("faults", {}) if isinstance(state.get("faults"), dict) else {}
    total_bytes = _to_int(counters.get("rx_total_bytes", 0), 0) + _to_int(counters.get("tx_total_bytes", 0), 0)
    return {
        "port": int(port),
        "reachable": bool(reachable),
        "protocol_state": _resolved_protocol_state_from_state(state),
        "boundary_kind": str(state.get("boundary_kind", "")),
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
        "phase": _resolved_phase_from_state(state),
        "current_missing_count": _false_unavailable_refs_from_state(state),
        "crash_sim": bool(faults.get("crash_sim", False)),
        "lie_sensor": bool(faults.get("lie_sensor", False)),
        "flap": bool(faults.get("flap", False)),
        "error": str(error or ""),
    }


def _all_node_rows(evidence):
    out = []
    for port in sorted(evidence.get("nodes", {}).keys(), key=lambda item: int(item)):
        node_info = evidence.get("nodes", {}).get(str(port), {})
        out.append(
            _node_row_from_state(
                port=port,
                reachable=node_info.get("reachable", False),
                state=node_info.get("state", {}),
                counters=node_info.get("msg_counters", {}),
                error=node_info.get("error", ""),
            )
        )
    return out


def _sample_nodes(base_port, number_of_nodes, sample_index, sample_sec):
    rows = []
    totals = {
        "sample_index": int(sample_index),
        "sample_sec": round(float(sample_sec), 3),
        "sample_label": "t+{:.1f}s".format(float(sample_sec)),
        "reachable_nodes": 0,
        "accepted_messages_total": 0,
        "pull_rx_total": 0,
        "push_rx_total": 0,
        "pull_tx_total": 0,
        "push_tx_total": 0,
        "rx_bytes_total": 0,
        "tx_bytes_total": 0,
        "total_bytes": 0,
        "total_mb": 0.0,
    }

    for port in range(int(base_port), int(base_port) + int(number_of_nodes)):
        try:
            res = _pull_state(port, origin="paper_history", timeout=0.75)
            state = res.get("data", {}).get("node_state", {}) if isinstance(res, dict) else {}
            counters = state.get("msg_counters", {}) if isinstance(state.get("msg_counters"), dict) else {}
            row = _node_row_from_state(port, True, state=state, counters=counters)
            totals["reachable_nodes"] += 1
        except Exception as exc:
            row = _node_row_from_state(port, False, state={}, counters={}, error=str(exc))

        row.update(
            {
                "sample_index": int(sample_index),
                "sample_sec": round(float(sample_sec), 3),
                "sample_label": "t+{:.1f}s".format(float(sample_sec)),
            }
        )
        rows.append(row)
        totals["accepted_messages_total"] += _to_int(row.get("accepted_messages", 0), 0)
        totals["pull_rx_total"] += _to_int(row.get("pull_rx", 0), 0)
        totals["push_rx_total"] += _to_int(row.get("push_rx", 0), 0)
        totals["pull_tx_total"] += _to_int(row.get("pull_tx", 0), 0)
        totals["push_tx_total"] += _to_int(row.get("push_tx", 0), 0)
        totals["rx_bytes_total"] += _to_int(row.get("rx_total_bytes", 0), 0)
        totals["tx_bytes_total"] += _to_int(row.get("tx_total_bytes", 0), 0)
        totals["total_bytes"] += _to_int(row.get("total_bytes", 0), 0)

    totals["total_mb"] = round(float(totals["total_bytes"]) / 1048576.0, 3)
    return rows, totals


def _metric_summary_rows(rows, fields):
    out = []
    for field in fields:
        values = []
        for row in rows:
            number = _maybe_float(row.get(field))
            if number is not None:
                values.append(float(number))
        if not values:
            continue
        out.append(
            {
                "metric": _field_label(field),
                "field": str(field),
                "samples": len(values),
                "avg": round(statistics.mean(values), 3),
                "min": round(min(values), 3),
                "max": round(max(values), 3),
                "latest": round(values[-1], 3),
            }
        )
    return out


def _series_points(rows, field, label_fn):
    points = []
    for idx, row in enumerate(rows):
        number = _maybe_float(row.get(field))
        if number is None:
            continue
        points.append((str(label_fn(row, idx)), float(number)))
    return points


def _delta_display(field, value):
    number = _maybe_float(value)
    if number is None:
        return "n/a"
    sign = "+" if float(number) > 0 else ""
    return "{}{}".format(sign, _format_display_value(field, float(number)))


def _series_records(points):
    records = []
    prev_value = None
    for idx, (label, value) in enumerate(points):
        delta = None if prev_value is None else float(value) - float(prev_value)
        records.append(
            {
                "index": int(idx),
                "label": str(label),
                "value": float(value),
                "delta": None if delta is None else float(delta),
            }
        )
        prev_value = float(value)
    return records


def _series_svg(points, color, field):
    if not points:
        return '<div class="chart-empty">No data</div>'

    records = _series_records(points)
    width = 360.0
    height = 150.0
    pad_x = 14.0
    pad_top = 14.0
    pad_bottom = 22.0
    pad_y = 10.0
    values = [float(value) for _, value in points]
    min_v = min(values)
    max_v = max(values)
    if abs(max_v - min_v) < 1e-9:
        max_v = min_v + 1.0
    usable_w = width - (pad_x * 2.0)
    usable_h = height - pad_top - pad_bottom - pad_y
    step_x = usable_w / max(1, len(points) - 1)

    coords = []
    fill_coords = []
    for idx, record in enumerate(records):
        value = float(record["value"])
        x = pad_x + (idx * step_x if len(points) > 1 else usable_w / 2.0)
        ratio = (float(value) - min_v) / (max_v - min_v)
        y = pad_top + ((1.0 - ratio) * usable_h)
        coords.append((x, y, record))
        fill_coords.append("{:.2f},{:.2f}".format(x, y))

    polyline = " ".join("{:.2f},{:.2f}".format(x, y) for x, y, _ in coords)
    fill_poly = " ".join(
        ["{:.2f},{:.2f}".format(coords[0][0], height - pad_bottom)]
        + fill_coords
        + ["{:.2f},{:.2f}".format(coords[-1][0], height - pad_bottom)]
    )
    circles = []
    for x, y, record in coords:
        label = str(record.get("label", ""))
        value = float(record.get("value", 0.0))
        delta = record.get("delta")
        value_display = _format_display_value(field, round(value, 3))
        delta_display = "start"
        if delta is not None:
            delta_display = _delta_display(field, round(float(delta), 3))
        title = "{} | {} | delta {}".format(label, value_display, delta_display)
        circles.append(
            '<circle cx="{x:.2f}" cy="{y:.2f}" r="3.2" fill="{color}" class="chart-point" tabindex="0" data-label="{label}" data-value="{value}" data-delta="{delta}" data-value-display="{value_display}" data-delta-display="{delta_display}"><title>{title}</title></circle>'.format(
                x=x,
                y=y,
                color=escape(color),
                label=escape(label),
                value=escape(str(round(value, 3))),
                delta=escape("" if delta is None else str(round(float(delta), 3))),
                value_display=escape(str(value_display)),
                delta_display=escape(str(delta_display)),
                title=escape(title),
            )
        )
    return """<svg viewBox="0 0 {w} {h}" class="metric-chart" role="img" aria-label="metric chart">
  <line x1="{px}" y1="{base}" x2="{wx}" y2="{base}" class="chart-axis"></line>
  <line x1="{px}" y1="{pt}" x2="{px}" y2="{base}" class="chart-axis"></line>
  <polygon points="{fill_poly}" fill="{color}" opacity="0.12"></polygon>
  <polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>
  {circles}
</svg>""".format(
        w=int(width),
        h=int(height),
        px=pad_x,
        pt=pad_top,
        wx=width - pad_x,
        base=height - pad_bottom,
        fill_poly=fill_poly,
        polyline=polyline,
        circles="".join(circles),
        color=escape(color),
    )


def _matplotlib_pyplot():
    cache_dir = ROOT_DIR / ".mplcache"
    cache_dir.mkdir(exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _write_line_figure(export_dir, stem, rows, field, label_fn, title, color="#2474e5"):
    points = _series_points(rows, field, label_fn)
    if not points:
        return None
    export_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = export_dir / "{}.tsv".format(stem)
    png_path = export_dir / "{}.png".format(stem)
    _write_tsv(
        tsv_path,
        [{"label": label, "value": round(value, 3)} for label, value in points],
        ["label", "value"],
    )
    plt = _matplotlib_pyplot()
    fig, ax = plt.subplots(figsize=(8.8, 4.8), dpi=180)
    x = list(range(len(points)))
    y = [value for _, value in points]
    ax.plot(x, y, marker="o", linewidth=2.3, markersize=4.5, color=color)
    ax.fill_between(x, y, color=color, alpha=0.12)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlabel("Sample")
    ax.set_ylabel(_field_label(field))
    if len(points) <= 12:
        ticks = x
    else:
        step = max(1, len(points) // 10)
        ticks = list(range(0, len(points), step))
        if ticks[-1] != x[-1]:
            ticks.append(x[-1])
    ax.set_xticks(ticks)
    ax.set_xticklabels([points[idx][0] for idx in ticks], rotation=35, ha="right", fontsize=8)
    ax.grid(True, axis="y", linestyle="--", alpha=0.3)
    fig.tight_layout()
    fig.savefig(png_path)
    plt.close(fig)
    return {
        "png": "figure_exports/{}.png".format(stem),
        "tsv": "figure_exports/{}.tsv".format(stem),
    }


def _write_timeline_figure(export_dir, timeline_rows):
    rows = [row for row in timeline_rows if _maybe_float(row.get("time_sec")) is not None]
    export_dir.mkdir(parents=True, exist_ok=True)
    tsv_path = export_dir / "timeline.tsv"
    png_path = export_dir / "timeline.png"
    _write_tsv(tsv_path, timeline_rows, TIMELINE_FIELDS)
    if not rows:
        return {"png": "", "tsv": "figure_exports/timeline.tsv"}
    plt = _matplotlib_pyplot()
    fig, ax = plt.subplots(figsize=(8.8, 3.8), dpi=180)
    y_positions = list(range(len(rows)))
    x_values = [_to_float(row.get("time_sec", 0.0), 0.0) for row in rows]
    labels = [str(row.get("milestone", "")) for row in rows]
    ax.hlines(y_positions, 0, x_values, color="#d9e1ef", linewidth=2.0)
    ax.scatter(x_values, y_positions, color="#118a7e", s=52, zorder=3)
    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Seconds into run")
    ax.set_title("Run Timeline", fontsize=12, fontweight="bold")
    ax.grid(True, axis="x", linestyle="--", alpha=0.25)
    fig.tight_layout()
    fig.savefig(png_path)
    plt.close(fig)
    return {
        "png": "figure_exports/timeline.png",
        "tsv": "figure_exports/timeline.tsv",
    }


def _write_figure_readme(export_dir, title, lines):
    export_dir.mkdir(parents=True, exist_ok=True)
    readme_path = export_dir / "README.md"
    content = ["# {}".format(title), ""] + ["- {}".format(line) for line in lines]
    _write_text(readme_path, "\n".join(content) + "\n")
    return "figure_exports/README.md"


def _write_run_figure_exports(run_dir, history_totals_rows, local_history, far_history, timeline_rows):
    export_dir = run_dir / "figure_exports"
    links = []
    created = []
    for payload in [
        _write_timeline_figure(export_dir, timeline_rows),
        _write_line_figure(export_dir, "network_total_mb", history_totals_rows, "total_mb", _sample_label, "Network Total MB Over Time", color="#ff7a59"),
        _write_line_figure(export_dir, "local_watch_total_mb", local_history, "total_mb", _sample_label, "Local Watch MB Over Time", color="#c58f10"),
        _write_line_figure(export_dir, "far_watch_total_mb", far_history, "total_mb", _sample_label, "Far Watch MB Over Time", color="#2474e5"),
        _write_line_figure(export_dir, "local_watch_msgs", local_history, "accepted_messages", _sample_label, "Local Watch Accepted Messages", color="#118a7e"),
    ]:
        if not payload:
            continue
        if payload.get("png"):
            links.append((Path(payload["png"]).name, payload["png"]))
            created.append(payload["png"])
        if payload.get("tsv"):
            links.append((Path(payload["tsv"]).name, payload["tsv"]))
            created.append(payload["tsv"])
    readme_href = _write_figure_readme(export_dir, "Run Figure Exports", created or ["No figures were generated for this run."])
    links.insert(0, ("figure_exports/README.md", readme_href))
    return links


def _write_suite_figure_exports(report_dir, summary_rows):
    export_dir = report_dir / "figure_exports"
    links = []
    created = []
    figure_specs = [
        ("suite_total_mb", "total_mb", "Suite Total MB By Run", "#ff7a59"),
        ("suite_detection_speed", "detection_speed_sec", "Suite Detection Speed By Run", "#2474e5"),
        ("suite_failures", "tx_fail_total", "Suite TX Failures By Run", "#c73a3a"),
        ("suite_false_positive_nodes", "false_positive_nodes", "Suite False Positive Nodes By Run", "#8b4cd6"),
        ("suite_false_unavailable_refs", "false_unavailable_refs", "Suite False Unavailable Refs By Run", "#c58f10"),
        ("suite_settle_accuracy", "settle_accuracy_pct", "Suite Settle Accuracy By Run", "#118a7e"),
    ]
    for stem, field, title, color in figure_specs:
        payload = _write_line_figure(export_dir, stem, summary_rows, field, _run_label, title, color=color)
        if not payload:
            continue
        links.append((Path(payload["png"]).name, payload["png"]))
        links.append((Path(payload["tsv"]).name, payload["tsv"]))
        created.extend([payload["png"], payload["tsv"]])
    readme_href = _write_figure_readme(export_dir, "Suite Figure Exports", created or ["No figures were generated for this suite."])
    links.insert(0, ("figure_exports/README.md", readme_href))
    return links


def _render_chart_grid_html(title, rows, fields, label_fn, subtitle=""):
    colors = ["#2474e5", "#118a7e", "#c58f10", "#c73a3a", "#8b4cd6", "#ff7a59"]
    charts = []
    for idx, field in enumerate(fields):
        points = _series_points(rows, field, label_fn)
        if not points:
            continue
        records = _series_records(points)
        values = [value for _, value in points]
        rises = [record for record in records if record.get("delta") is not None and float(record.get("delta")) > 0]
        drops = [record for record in records if record.get("delta") is not None and float(record.get("delta")) < 0]
        biggest_rise = max(rises, key=lambda item: float(item.get("delta", 0.0))) if rises else None
        biggest_drop = min(drops, key=lambda item: float(item.get("delta", 0.0))) if drops else None
        rise_html = (
            '<span class="chart-pill good">Rise {} at {}</span>'.format(
                escape(_delta_display(field, biggest_rise.get("delta"))),
                escape(str(biggest_rise.get("label", ""))),
            )
            if biggest_rise
            else '<span class="chart-pill soft">No rise detected</span>'
        )
        drop_html = (
            '<span class="chart-pill bad">Drop {} at {}</span>'.format(
                escape(_delta_display(field, biggest_drop.get("delta"))),
                escape(str(biggest_drop.get("label", ""))),
            )
            if biggest_drop
            else '<span class="chart-pill soft">No drop detected</span>'
        )
        charts.append(
            """<div class="chart-card interactive-chart-card">
  <div class="chart-title">{title}</div>
  <div class="chart-stats">avg {avg} | min {minv} | max {maxv}</div>
  <div class="chart-annotations">{rise}{drop}</div>
  {svg}
  <div class="chart-detail">Hover or click a point to see the exact label, value, and delta.</div>
  <div class="chart-footer">{first} to {last}</div>
</div>""".format(
                title=escape(_field_label(field)),
                avg=escape(_format_display_value(field, round(statistics.mean(values), 3))),
                minv=escape(_format_display_value(field, round(min(values), 3))),
                maxv=escape(_format_display_value(field, round(max(values), 3))),
                rise=rise_html,
                drop=drop_html,
                svg=_series_svg(points, colors[idx % len(colors)], field),
                first=escape(points[0][0]),
                last=escape(points[-1][0]),
            )
        )

    subtitle_html = '<p class="section-note">{}</p>'.format(escape(subtitle)) if subtitle else ""
    content = "".join(charts) if charts else '<div class="chart-empty">No chart data available.</div>'
    return """<section class="panel">
<div class="panel-head">
  <h2>{title}</h2>
  {subtitle}
</div>
<div class="chart-grid">{content}</div>
</section>""".format(title=escape(title), subtitle=subtitle_html, content=content)


def _run_label(row, _idx):
    return "N{} R{}".format(_format_display_value("nodes", row.get("nodes", "")), _format_display_value("run_index", row.get("run_index", "")))


def _sample_label(row, _idx):
    return str(row.get("sample_label", ""))


def _node_spotlight_payload(evidence, watch_ports=None):
    watch_map = {}
    if isinstance(watch_ports, dict):
        for label, port in watch_ports.items():
            port_int = _maybe_int(port)
            if port_int is not None:
                watch_map[int(port_int)] = str(label).strip().upper()
    payload = []
    for port in sorted(evidence.get("nodes", {}).keys(), key=lambda item: int(item)):
        node_info = evidence.get("nodes", {}).get(str(port), {})
        state = node_info.get("state", {}) if isinstance(node_info.get("state"), dict) else {}
        counters = node_info.get("msg_counters", {}) if isinstance(node_info.get("msg_counters"), dict) else {}
        row = _node_row_from_state(
            port=port,
            reachable=node_info.get("reachable", False),
            state=state,
            counters=counters,
            error=node_info.get("error", ""),
        )
        row["recent_msgs"] = state.get("recent_msgs", [])[-15:] if isinstance(state.get("recent_msgs"), list) else []
        row["recent_alerts"] = state.get("recent_alerts", [])[-10:] if isinstance(state.get("recent_alerts"), list) else []
        row["pull_cycles"] = _to_int(state.get("pull_cycles", 0), 0)
        row["incoming_events_count"] = len(state.get("incoming_events", [])) if isinstance(state.get("incoming_events"), list) else 0
        row["known_nodes_count"] = len(state.get("known_nodes", [])) if isinstance(state.get("known_nodes"), list) else 0
        row["watch_role"] = watch_map.get(int(row["port"]), "")
        summary_bits = [str(row["port"])]
        if row["watch_role"]:
            summary_bits.append("{} watch".format(str(row["watch_role"]).title()))
        if str(row.get("protocol_state", "")).strip():
            summary_bits.append(str(row.get("protocol_state", "")).strip())
        summary_bits.append("{:.3f} MB".format(_to_float(row.get("total_mb", 0.0), 0.0)))
        row["summary_label"] = " · ".join(summary_bits)
        payload.append(row)
    return payload


def _render_field_reference_html():
    groups = [
        (
            "Core Terms",
            [
                ("TX", "Traffic sent by the node."),
                ("RX", "Traffic received by the node."),
                ("Pull", "Polling traffic where one node asks another node for state."),
                ("Push", "Dissemination traffic sent without first being asked."),
                ("LOCAL", "The watched node closest to the scenario focus or first impact area."),
                ("FAR", "The watched node farthest from LOCAL, useful for propagation and scaling."),
            ],
        ),
        (
            "Run Summary",
            [
                ("Phase", "The experiment family, such as baseline, fire, tornado, or stress."),
                ("Challenge", "The exact scenario pattern used in this run."),
                ("Nodes", "How many nodes were started for the run."),
                ("Run", "The repetition number inside the suite."),
                ("Seed", "The deterministic seed used to make paired comparisons fair."),
                ("Active Time", "The measured scenario window that actually ran."),
                ("Reachable", "How many nodes answered when evidence was collected."),
                ("Total Nodes", "How many nodes were expected in the network."),
                ("Events", "Logged scenario actions such as stage changes, faults, or resets."),
                ("Detection Speed", "Seconds until the LOCAL watch first shows a hazard signal."),
                ("First Watch / First Impact / Outage / Recovery / Reset", "The key timeline milestones pulled into the run timeline strip."),
                ("TX Fail / TX Timeout / Conn Err", "Send-side problems seen during the run."),
                ("Status", "Overall outcome, usually OK, WARN, or FAIL."),
            ],
        ),
        (
            "Message Flow",
            [
                ("Accepted Msgs", "Messages the protocol accepted into node state or processing."),
                ("Pull RX", "Pull requests this node received and answered."),
                ("Pull TX", "Pull requests this node sent to other nodes."),
                ("Push RX", "Protocol push messages this node received."),
                ("Push TX", "Protocol push messages this node sent."),
            ],
        ),
        (
            "Traffic And Overhead",
            [
                ("RX Bytes", "Total bytes received by the node."),
                ("TX Bytes", "Total bytes sent by the node."),
                ("Bytes", "RX Bytes plus TX Bytes."),
                ("MB", "Bytes converted to megabytes for paper-friendly reading."),
            ],
        ),
        (
            "Residual Quality",
            [
                ("False Positive Nodes", "Nodes that still look non-normal at the end of the run when they should have settled."),
                ("False Unavailable Refs", "Neighbor references that still look unavailable even though evidence collection reached the full network."),
                ("Settle Accuracy", "A paper-friendly final-state accuracy proxy computed from how many nodes returned to normal."),
            ],
        ),
        (
            "State And Faults",
            [
                ("State", "The node's current protocol state."),
                ("Boundary Kind", "The local boundary interpretation, such as stable or front."),
                ("Phase", "The current sensing phase, such as CLEAR or impact-related states."),
                ("Direction", "The inferred hazard direction when the protocol supports it."),
                ("Missing", "How many neighbors are currently missing or marked unavailable."),
                ("Crash Sim", "An injected false-unavailability fault."),
                ("Lie Sensor", "An injected misleading sensor-reading fault."),
                ("Flap", "An injected on-off or unstable behavior fault."),
                ("Error", "The last reporting or pull error captured for that node."),
            ],
        ),
    ]

    cards = []
    for title, items in groups:
        bullets = "".join(
            '<li><strong>{}</strong>: {}</li>'.format(escape(name), escape(desc))
            for name, desc in items
        )
        cards.append(
            """<div class="guide-list-card">
  <h3>{}</h3>
  <ul class="guide-list">{}</ul>
</div>""".format(escape(title), bullets)
        )

    return """<section class="panel">
<div class="panel-head">
  <h2>Field Reference</h2>
  <p class="section-note">This explains the main variables used in the run table, watched-node table, history charts, and all-node snapshot.</p>
</div>
<div class="guide-list-grid">{}</div>
</section>""".format("".join(cards))


def _render_glossary_html():
    cards = [
        (
            "LOCAL vs FAR",
            "LOCAL is the watched node closest to the scenario focus. FAR is the watched node farthest from LOCAL, which helps show propagation instead of direct impact.",
        ),
        (
            "Speed",
            "Use active time, early chart slope, accepted messages, and pull or push growth to see how quickly information spreads and stabilizes.",
        ),
        (
            "Resilience",
            "Use reachable nodes, TX failures, TX timeouts, missing neighbors, false-unavailable references, and active fault flags to judge how well the protocol handles stress.",
        ),
        (
            "Overhead",
            "Use total bytes, total MB, pull RX or TX, and push RX or TX to measure message cost on a node or across a run.",
        ),
        (
            "Scalability",
            "Compare the grouped node-count table and suite charts as 49, 64, or 81 nodes grow. Linear growth is usually easier to defend in the paper.",
        ),
        (
            "Correlation",
            "Treat correlation as pattern matching, not proof. If TX failures rise with MB, retries are likely adding cost. If accepted messages rise with push RX, dissemination is intensifying.",
        ),
    ]

    guide_rows = [
        ("Speed", "active_duration_sec, accepted_messages, pull or push history", "Faster runs usually show earlier, steeper growth with fewer stalls."),
        ("Resilience", "reachable_nodes, tx_fail_total, tx_timeout_total, current_missing_count, false_unavailable_refs", "More failures or missing neighbors usually means weaker fault tolerance."),
        ("Overhead", "total_mb, total_bytes, pull_rx or tx, push_rx or tx", "Lower MB with similar coverage is a stronger efficiency story."),
        ("Accuracy", "phase, direction_label, boundary_kind, false_positive_nodes, settle_accuracy_pct", "Consistency, correct state interpretation, and low residual alerts support stronger hazard sensing claims."),
        ("Correlation", "compare chart pairs like failures vs MB, accepted_messages vs push_rx", "Look for metrics rising or falling together, then confirm with scenario context."),
    ]

    card_html = "".join(
        '<div class="guide-card"><h3>{}</h3><p>{}</p></div>'.format(escape(title), escape(body))
        for title, body in cards
    )
    row_html = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(escape(goal), escape(metrics), escape(reading))
        for goal, metrics, reading in guide_rows
    )
    return """<section class="panel">
<div class="panel-head">
  <h2>Metric Guide</h2>
  <p class="section-note">This is the legend for reading the dashboard and the paper figures.</p>
</div>
<div class="guide-grid">{}</div>
<table class="guide-table">
  <thead><tr><th>Goal</th><th>Main Metrics</th><th>How To Read It</th></tr></thead>
  <tbody>{}</tbody>
</table>
</section>""".format(card_html, row_html)


def _render_timeline_panel(timeline_rows):
    if not timeline_rows:
        return ""

    items = []
    for row in timeline_rows:
        status = str(row.get("status", "")).strip().lower()
        badge = "pill-soft"
        if status == "observed":
            badge = "pill-good"
        elif status and status != "n/a":
            badge = "pill-warn"
        items.append(
            """<div class="timeline-item">
  <div class="timeline-dot"></div>
  <div class="timeline-card">
    <div class="timeline-top">
      <h3>{milestone}</h3>
      <span class="badge {badge}">{status}</span>
    </div>
    <div class="timeline-time">{time_value}</div>
    <div class="timeline-detail">{detail}</div>
  </div>
</div>""".format(
                milestone=escape(str(row.get("milestone", ""))),
                badge=badge,
                status=escape(str(row.get("status", "") or "n/a")),
                time_value=escape(_format_display_value("time_sec", row.get("time_sec", "")) or "n/a"),
                detail=escape(str(row.get("detail", "") or "No detail recorded")),
            )
        )

    return """<section class="panel">
<div class="panel-head">
  <h2>True Event Timeline</h2>
  <p class="section-note">This strip lines up the scenario milestones that matter most for speed and resilience: ignition, first watch, first impact, outage, recovery, and reset.</p>
</div>
<div class="timeline-strip">{items}</div>
<div class="table-wrap" style="margin-top:14px;">
  <table>
    <thead><tr><th>Milestone</th><th>Time</th><th>Status</th><th>Detail</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
</section>""".format(
        items="".join(items),
        rows="".join(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                escape(str(row.get("milestone", ""))),
                escape(_format_display_value("time_sec", row.get("time_sec", "")) or "n/a"),
                escape(str(row.get("status", "") or "n/a")),
                escape(str(row.get("detail", "") or "")),
            )
            for row in timeline_rows
        ),
    )


def _render_fire_semantics_panel(fire_stage_rows):
    if not fire_stage_rows:
        return ""
    rows_html = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            escape(str(row.get("stage", ""))),
            escape(str(row.get("time_window", "") or "n/a")),
            escape(str(row.get("affected_ports", "") or "n/a")),
            escape(str(row.get("detail", "") or "")),
        )
        for row in fire_stage_rows
    )
    return """<section class="panel fire-panel">
<div class="panel-head">
  <h2>Fire Semantics</h2>
  <p class="section-note">This run uses a spreading fire front with four paper-friendly stages: ignition, front expansion, bomb core, and recovery.</p>
</div>
<div class="guide-grid">
  <div class="guide-card"><h3>Ignition</h3><p>The first center ignition point that starts the spread.</p></div>
  <div class="guide-card"><h3>Front Expansion</h3><p>Hop-based outward rings that show how the fire front propagates through the topology.</p></div>
  <div class="guide-card"><h3>Bomb Core</h3><p>A short, concentrated impact near the center that stresses sudden local unavailability.</p></div>
  <div class="guide-card"><h3>Recovery</h3><p>Recovery waves and the final reset that should bring nodes back toward normal.</p></div>
</div>
<div class="table-wrap" style="margin-top:14px;">
  <table>
    <thead><tr><th>Stage</th><th>Time Window</th><th>Affected Ports</th><th>Detail</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
</section>""".format(rows=rows_html)


def _render_spotlight_table_html(title, rows, fields, port_field, subtitle=""):
    head = []
    for field in fields:
        head.append("<th>{}</th>".format(escape(_field_label(field))))

    body = []
    if rows:
        for row in rows:
            cells = []
            for field in fields:
                display = escape(_format_display_value(field, row.get(field, "")))
                badge_class = _badge_class(field, row.get(field, ""))
                if badge_class:
                    display = '<span class="badge {}">{}</span>'.format(badge_class, display)
                cells.append('<td class="{}">{}</td>'.format(_cell_class(field, row.get(field, "")), display))

            row_classes = _row_class(row)
            attrs = ""
            port_value = _maybe_int(row.get(port_field, ""))
            if port_value is not None:
                row_classes = "{} spotlight-row-selectable".format(row_classes).strip()
                attrs = ' data-spotlight-port="{port}" tabindex="0" role="button" aria-label="Select node {port} for spotlight"'.format(
                    port=escape(str(port_value))
                )
            body.append('<tr class="{classes}"{attrs}>{cells}</tr>'.format(classes=row_classes, attrs=attrs, cells="".join(cells)))
    else:
        body.append('<tr><td colspan="{}" class="empty">No rows recorded.</td></tr>'.format(len(fields)))

    subtitle_html = ""
    if subtitle:
        subtitle_html = '<p class="section-note">{}</p>'.format(escape(subtitle))

    return """<section class="panel">
<div class="panel-head">
  <h2>{title}</h2>
  {subtitle}
</div>
<div class="table-wrap">
  <table>
    <thead><tr>{head}</tr></thead>
    <tbody>{body}</tbody>
  </table>
</div>
</section>""".format(
        title=escape(title),
        subtitle=subtitle_html,
        head="".join(head),
        body="".join(body),
    )


def _read_tsv_rows(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _comparison_report_roots():
    candidates = [
        REPORTS_DIR,
        ROOT_DIR / "external" / "checkin-egess-eval" / "paper_reports",
        ROOT_DIR.parent.parent / "paper_reports",
    ]
    roots = []
    seen = set()
    for path in candidates:
        if not path.exists() or not path.is_dir():
            continue
        resolved = str(path.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        roots.append(path)
    return roots


def _scenario_label(phase_id, challenge):
    labels = {
        "steady_state_baseline": "Baseline",
        "firebomb": "Fire",
        "tornado_sweep": "Tornado",
        "ghost_outage_noise": "Ghost Outage + Noise",
    }
    text = labels.get(str(challenge).strip(), "")
    if text:
        return text
    if str(challenge).strip():
        return str(challenge).replace("_", " ").title()
    return str(phase_id).replace("_", " ").title()


def _scenario_sort_key(signature):
    phase_id, challenge = signature
    phase_order = {"phase1": 1, "phase2": 2, "phase3": 3, "phase4": 4}
    return (phase_order.get(str(phase_id), 99), _scenario_label(phase_id, challenge))


def _suite_setup_parts(rows):
    nodes = sorted({_to_int(row.get("nodes", 0), 0) for row in rows if _to_int(row.get("nodes", 0), 0) > 0})
    durations = sorted({int(round(_to_float(row.get("duration_sec", 0.0), 0.0))) for row in rows if _to_float(row.get("duration_sec", 0.0), 0.0) > 0})
    node_label = "mixed"
    if len(nodes) == 1:
        node_label = "N{}".format(nodes[0])
    elif nodes:
        node_label = "N{}".format("/".join(str(value) for value in nodes))
    duration_label = "mixed"
    if len(durations) == 1:
        duration_label = "{}s".format(durations[0])
    elif durations:
        duration_label = "/".join("{}s".format(value) for value in durations)
    return node_label, duration_label, tuple(nodes), tuple(durations)


def _row_has_signal(row):
    return _history_row_has_hazard_signal(row)


def _run_detection_speed_sec(repo_root, summary_row):
    run_dir_value = str(summary_row.get("run_dir", "")).strip()
    if not run_dir_value:
        return None
    local_port = _to_int(summary_row.get("local_watch_port", 0), 0)
    if local_port <= 0:
        return None
    history_path = repo_root / run_dir_value / "paper_pull_history.tsv"
    history_rows = _read_tsv_rows(history_path)
    if not history_rows:
        return None
    port_rows = []
    for row in history_rows:
        if _to_int(row.get("port", -1), -1) != local_port:
            continue
        if str(row.get("error", "")).strip():
            continue
        port_rows.append(row)
    if not port_rows:
        return None
    port_rows.sort(key=lambda row: (_to_int(row.get("sample_index", 0), 0), _to_float(row.get("sample_sec", 0.0), 0.0)))
    if _row_has_signal(port_rows[0]):
        return 0.0
    for row in port_rows[1:]:
        if _row_has_signal(row):
            return _to_float(row.get("sample_sec", 0.0), 0.0)
    return None


def _latest_protocol_suite_index():
    suites_by_protocol = {}
    for report_root in _comparison_report_roots():
        repo_root = report_root.parent
        for suite_dir in sorted(report_root.iterdir()):
            if not suite_dir.is_dir():
                continue
            rows = _read_tsv_rows(suite_dir / "all_runs.tsv")
            if not rows:
                continue
            row0 = rows[0]
            protocol = str(row0.get("protocol", "")).strip().lower()
            if not protocol:
                continue
            signature = (str(row0.get("phase_id", "")).strip(), str(row0.get("challenge", "")).strip())
            entry = {
                "report_dir": suite_dir,
                "repo_root": repo_root,
                "rows": rows,
                "mtime": suite_dir.stat().st_mtime,
            }
            protocol_map = suites_by_protocol.setdefault(protocol, {})
            existing = protocol_map.get(signature)
            if existing is None or entry["mtime"] > existing["mtime"]:
                protocol_map[signature] = entry
    return suites_by_protocol


def _suite_comparison_metrics(entry):
    rows = entry.get("rows", [])
    repo_root = entry.get("repo_root")
    if not rows or repo_root is None:
        return None
    total_bytes_values = [_to_float(row.get("total_bytes", 0.0), 0.0) for row in rows]
    total_mb_values = [_to_float(row.get("total_mb", 0.0), 0.0) for row in rows]
    failure_values = [
        _to_float(row.get("tx_fail_total", 0.0), 0.0)
        + _to_float(row.get("tx_timeout_total", 0.0), 0.0)
        + _to_float(row.get("tx_conn_error_total", 0.0), 0.0)
        for row in rows
    ]
    detection_values = []
    for row in rows:
        detection = _run_detection_speed_sec(repo_root, row)
        if detection is not None:
            detection_values.append(float(detection))
    node_label, duration_label, node_key, duration_key = _suite_setup_parts(rows)
    return {
        "setup": "{} · {} · {} runs".format(node_label, duration_label, len(rows)),
        "setup_key": (node_key, duration_key),
        "avg_total_bytes": statistics.mean(total_bytes_values) if total_bytes_values else 0.0,
        "avg_total_mb": statistics.mean(total_mb_values) if total_mb_values else 0.0,
        "avg_failures": statistics.mean(failure_values) if failure_values else 0.0,
        "avg_detection_speed": statistics.mean(detection_values) if detection_values else None,
    }


def _build_protocol_comparison_rows():
    suites_by_protocol = _latest_protocol_suite_index()
    signatures = set()
    for protocol_suites in suites_by_protocol.values():
        signatures.update(protocol_suites.keys())

    rows = []
    for signature in sorted(signatures, key=_scenario_sort_key):
        phase_id, challenge = signature
        egess_entry = suites_by_protocol.get("egess", {}).get(signature)
        checkin_entry = suites_by_protocol.get("checkin", {}).get(signature)
        egess_metrics = _suite_comparison_metrics(egess_entry) if egess_entry else None
        checkin_metrics = _suite_comparison_metrics(checkin_entry) if checkin_entry else None

        if egess_metrics is None and checkin_metrics is None:
            continue

        status = "Fair"
        note = "Ready for paper comparison."
        if egess_metrics is None or checkin_metrics is None:
            status = "Missing"
            note = "One protocol has not produced this scenario yet."
        elif egess_metrics.get("setup_key") != checkin_metrics.get("setup_key"):
            status = "Mismatch"
            note = "Match node count and duration before using this row in the paper."
        elif egess_metrics.get("avg_detection_speed") is None or checkin_metrics.get("avg_detection_speed") is None:
            note = "Detection speed needs fresh history-enabled runs for both protocols."

        rows.append(
            {
                "scenario_label": _scenario_label(phase_id, challenge),
                "egess_setup": egess_metrics.get("setup", "n/a") if egess_metrics else "n/a",
                "egess_bytes": (
                    "{:,.0f} B ({:.3f} MB)".format(egess_metrics.get("avg_total_bytes", 0.0), egess_metrics.get("avg_total_mb", 0.0))
                    if egess_metrics
                    else "n/a"
                ),
                "egess_failures": "{:.2f} / run".format(egess_metrics.get("avg_failures", 0.0)) if egess_metrics else "n/a",
                "egess_detection_speed": (
                    "{:.2f}s".format(egess_metrics.get("avg_detection_speed"))
                    if egess_metrics and egess_metrics.get("avg_detection_speed") is not None
                    else "n/a"
                ),
                "checkin_setup": checkin_metrics.get("setup", "n/a") if checkin_metrics else "n/a",
                "checkin_bytes": (
                    "{:,.0f} B ({:.3f} MB)".format(checkin_metrics.get("avg_total_bytes", 0.0), checkin_metrics.get("avg_total_mb", 0.0))
                    if checkin_metrics
                    else "n/a"
                ),
                "checkin_failures": "{:.2f} / run".format(checkin_metrics.get("avg_failures", 0.0)) if checkin_metrics else "n/a",
                "checkin_detection_speed": (
                    "{:.2f}s".format(checkin_metrics.get("avg_detection_speed"))
                    if checkin_metrics and checkin_metrics.get("avg_detection_speed") is not None
                    else "n/a"
                ),
                "comparison_status": status,
                "comparison_note": note,
            }
        )
    return rows


def _render_comparison_panel(comparison_rows):
    if not comparison_rows:
        return (
            """<section class="panel">
<div class="panel-head">
  <h2>Comparison Between Protocols</h2>
  <p class="section-note">Run both protocols first, then this section will compare the latest matching scenario suites.</p>
</div>
<div class="empty">No protocol comparison rows are available yet.</div>
</section>""",
            "",
        )

    scenario_order = ["Baseline", "Tornado", "Fire", "Bomb", "Ghost Outage + Noise"]
    seen = []
    for label in scenario_order + [row.get("scenario_label", "") for row in comparison_rows]:
        text = str(label).strip()
        if text and text not in seen:
            seen.append(text)

    button_html = ['<button type="button" class="scenario-tab active" data-scenario-filter="ALL">All</button>']
    for label in seen:
        slug = label.lower().replace(" ", "-").replace("+", "plus")
        button_html.append(
            '<button type="button" class="scenario-tab" data-scenario-filter="{slug}">{label}</button>'.format(
                slug=escape(slug),
                label=escape(label),
            )
        )

    head = "".join("<th>{}</th>".format(escape(_field_label(field))) for field in COMPARISON_FIELDS)
    body_rows = []
    for row in comparison_rows:
        scenario = str(row.get("scenario_label", "")).strip()
        slug = scenario.lower().replace(" ", "-").replace("+", "plus")
        cells = []
        for field in COMPARISON_FIELDS:
            display = escape(_format_display_value(field, row.get(field, "")))
            badge_class = _badge_class(field, row.get(field, ""))
            if badge_class:
                display = '<span class="badge {}">{}</span>'.format(badge_class, display)
            cells.append('<td class="{}">{}</td>'.format(_cell_class(field, row.get(field, "")), display))
        body_rows.append(
            '<tr class="{classes}" data-scenario="{scenario}">{cells}</tr>'.format(
                classes=_row_class(row),
                scenario=escape(slug),
                cells="".join(cells),
            )
        )

    panel_html = """<section class="panel">
<div class="panel-head">
  <h2>Comparison Between Protocols</h2>
  <p class="section-note">Detection speed uses the first LOCAL watch-node signal after scenario start. Use rows marked Fair for paper-ready comparisons.</p>
</div>
<div class="scenario-tab-row">{buttons}</div>
<div class="table-wrap">
  <table id="comparison-table">
    <thead><tr>{head}</tr></thead>
    <tbody>{body}</tbody>
  </table>
</div>
</section>""".format(buttons="".join(button_html), head=head, body="".join(body_rows))

    script_html = """<script>
(function () {
  const buttons = Array.from(document.querySelectorAll('.scenario-tab'));
  const rows = Array.from(document.querySelectorAll('#comparison-table tbody tr'));
  if (!buttons.length || !rows.length) return;

  function applyFilter(filterValue) {
    rows.forEach((row) => {
      const scenario = row.getAttribute('data-scenario') || '';
      row.style.display = (filterValue === 'ALL' || scenario === filterValue) ? '' : 'none';
    });
    buttons.forEach((button) => {
      button.classList.toggle('active', button.getAttribute('data-scenario-filter') === filterValue);
    });
  }

  buttons.forEach((button) => {
    button.addEventListener('click', () => {
      applyFilter(button.getAttribute('data-scenario-filter') || 'ALL');
    });
  });

  applyFilter('ALL');
})();
</script>"""
    return panel_html, script_html


def _render_suite_interactive_panel(summary_rows):
    if not summary_rows:
        return "", ""

    options_html = "".join(
        '<option value="{value}">{label}</option>'.format(value=escape(field), label=escape(_field_label(field)))
        for field in SUMMARY_CHART_FIELDS
    )
    summary_json = escape(json.dumps(summary_rows))
    labels_json = escape(json.dumps({field: _field_label(field) for field in SUMMARY_CHART_FIELDS}))

    panel_html = """<section class="panel">
<div class="panel-head">
  <h2>Flexible Averages</h2>
  <p class="section-note">Type any run count like 5, 14, or 23 to recompute prefix averages without rerunning the suite.</p>
</div>
<div class="control-row">
  <div class="control-field">
    <label for="suite-window-input">Runs To Include</label>
    <input id="suite-window-input" type="number" min="1" step="1">
  </div>
  <div class="control-field">
    <label for="suite-metric-select">Metric To Graph</label>
    <select id="suite-metric-select">{}</select>
  </div>
</div>
<div id="suite-window-cards" class="micro-grid"></div>
<div class="spotlight-grid" style="margin-top:12px;">
  <div class="spotlight-card">
    <h3>Selected Metric Trend</h3>
    <div id="suite-window-chart"></div>
    <p id="suite-window-note" class="micro-note"></p>
  </div>
  <div class="spotlight-card">
    <h3>Prefix Average Summary</h3>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Metric</th><th>Value</th></tr></thead>
        <tbody id="suite-window-table"></tbody>
      </table>
    </div>
  </div>
</div>
</section>""".format(options_html)

    script_html = """<script type="application/json" id="suite-summary-data">{summary_json}</script>
<script type="application/json" id="suite-field-labels">{labels_json}</script>
<script>
(() => {{
  const rows = JSON.parse(document.getElementById('suite-summary-data').textContent || '[]');
  const labels = JSON.parse(document.getElementById('suite-field-labels').textContent || '{{}}');
  if (!rows.length) return;
  const input = document.getElementById('suite-window-input');
  const metricSelect = document.getElementById('suite-metric-select');
  const cardsHost = document.getElementById('suite-window-cards');
  const chartHost = document.getElementById('suite-window-chart');
  const tableHost = document.getElementById('suite-window-table');
  const noteHost = document.getElementById('suite-window-note');
  const intFmt = new Intl.NumberFormat('en-US');

  function toNum(value) {{
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
  }}

  function avg(field, subset) {{
    const values = subset.map(row => toNum(row[field])).filter(value => value !== null);
    if (!values.length) return null;
    return values.reduce((acc, value) => acc + value, 0) / values.length;
  }}

  function fmt(field, value) {{
    if (value === null || value === undefined || Number.isNaN(value)) return 'n/a';
    if (field === 'active_duration_sec' || field === 'duration_sec') return value.toFixed(3) + 's';
    if (field.endsWith('_mb')) return value.toFixed(3) + ' MB';
    if (field.includes('bytes')) return intFmt.format(Math.round(value));
    if (Math.abs(value - Math.round(value)) < 1e-9) return intFmt.format(Math.round(value));
    return value.toFixed(3);
  }}

  function lineSvg(points, color) {{
    if (!points.length) return '<div class="chart-empty">No data</div>';
    const width = 360;
    const height = 150;
    const padX = 14;
    const padTop = 14;
    const padBottom = 22;
    const values = points.map(point => point.value);
    let min = Math.min(...values);
    let max = Math.max(...values);
    if (Math.abs(max - min) < 1e-9) max = min + 1;
    const usableW = width - padX * 2;
    const usableH = height - padTop - padBottom - 10;
    const stepX = points.length > 1 ? usableW / (points.length - 1) : 0;
    const coords = points.map((point, idx) => {{
      const x = points.length > 1 ? padX + idx * stepX : padX + usableW / 2;
      const ratio = (point.value - min) / (max - min);
      const y = padTop + (1 - ratio) * usableH;
      return {{ x, y }};
    }});
    const polyline = coords.map(point => `${{point.x.toFixed(2)}},${{point.y.toFixed(2)}}`).join(' ');
    const fillPoly = [`${{coords[0].x.toFixed(2)}},${{(height - padBottom).toFixed(2)}}`]
      .concat(coords.map(point => `${{point.x.toFixed(2)}},${{point.y.toFixed(2)}}`))
      .concat([`${{coords[coords.length - 1].x.toFixed(2)}},${{(height - padBottom).toFixed(2)}}`])
      .join(' ');
    const circles = coords.map(point => `<circle cx="${{point.x.toFixed(2)}}" cy="${{point.y.toFixed(2)}}" r="2.8" fill="${{color}}"></circle>`).join('');
    return `<svg viewBox="0 0 ${{width}} ${{height}}" class="metric-chart" role="img" aria-label="metric chart">
      <line x1="${{padX}}" y1="${{height - padBottom}}" x2="${{width - padX}}" y2="${{height - padBottom}}" class="chart-axis"></line>
      <line x1="${{padX}}" y1="${{padTop}}" x2="${{padX}}" y2="${{height - padBottom}}" class="chart-axis"></line>
      <polygon points="${{fillPoly}}" fill="${{color}}" opacity="0.12"></polygon>
      <polyline points="${{polyline}}" fill="none" stroke="${{color}}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>
      ${{circles}}
    </svg>`;
  }}

  function render() {{
    const maxRuns = rows.length;
    let count = parseInt(input.value || maxRuns, 10);
    if (!Number.isFinite(count)) count = maxRuns;
    count = Math.max(1, Math.min(maxRuns, count));
    input.value = count;
    input.max = maxRuns;
    const subset = rows.slice(0, count);
    const metric = metricSelect.value || 'total_mb';
    const selectedAvg = avg(metric, subset);
    const selectedLatest = toNum(subset[subset.length - 1][metric]);
    const summaryCards = [
      {{ label: 'Runs Used', value: String(count), note: `of ${{maxRuns}} completed runs` }},
      {{ label: 'Avg Traffic', value: fmt('total_mb', avg('total_mb', subset)), note: 'selected prefix average' }},
      {{ label: 'Avg Failures', value: fmt('tx_fail_total', avg('tx_fail_total', subset)), note: 'TX failures per run' }},
      {{ label: 'Avg Reachable', value: fmt('reachable_nodes', avg('reachable_nodes', subset)), note: 'reachable nodes per run' }},
      {{ label: `Avg ${{labels[metric] || metric}}`, value: fmt(metric, selectedAvg), note: 'current selected metric' }},
    ];
    cardsHost.innerHTML = summaryCards.map(card => `<div class="micro-card"><div class="micro-label">${{card.label}}</div><div class="micro-value">${{card.value}}</div><div class="micro-note">${{card.note}}</div></div>`).join('');

    const points = subset
      .map(row => ({{ label: `R${{row.run_index}} @ N${{row.nodes}}`, value: toNum(row[metric]) }}))
      .filter(point => point.value !== null);
    chartHost.innerHTML = lineSvg(points, '#2474e5');
    noteHost.textContent = points.length
      ? `Showing the first ${{count}} runs. This is useful for checking early averages before all 30 runs finish.`
      : 'No numeric data for the selected metric.';

    const tableRows = [
      ['Average Traffic', fmt('total_mb', avg('total_mb', subset))],
      ['Average Failures', fmt('tx_fail_total', avg('tx_fail_total', subset))],
      ['Average Timeouts', fmt('tx_timeout_total', avg('tx_timeout_total', subset))],
      ['Average Reachable Nodes', fmt('reachable_nodes', avg('reachable_nodes', subset))],
      [`Average ${{labels[metric] || metric}}`, fmt(metric, selectedAvg)],
      [`Latest ${{labels[metric] || metric}}`, fmt(metric, selectedLatest)],
    ];
    tableHost.innerHTML = tableRows.map(([label, value]) => `<tr><td>${{label}}</td><td>${{value}}</td></tr>`).join('');
  }}

  input.value = rows.length;
  input.addEventListener('input', render);
  metricSelect.addEventListener('change', render);
  render();
}})();
</script>""".format(summary_json=summary_json, labels_json=labels_json)
    return panel_html, script_html


def _average_for_rows(rows, field):
    values = []
    for row in rows:
        number = _maybe_float(row.get(field))
        if number is not None:
            values.append(float(number))
    if not values:
        return None
    return float(statistics.mean(values))


def _render_nodecount_delta_html(field, current_value, reference_value):
    if current_value is None or reference_value is None:
        return '<span class="delta-chip delta-flat">n/a</span>'
    delta = float(current_value) - float(reference_value)
    if abs(delta) < 1e-12:
        return '<span class="delta-chip delta-flat">{}</span>'.format(escape(_format_display_value(field, 0)))

    display = _format_display_value(field, delta)
    delta_class = "delta-down"
    if delta > 0:
        display = "+{}".format(display)
        delta_class = "delta-up"

    pct_html = ""
    if abs(float(reference_value)) >= 1e-12:
        pct_html = '<span class="delta-subnote">({:+.1f}%)</span>'.format((delta / float(reference_value)) * 100.0)
    return '<span class="delta-chip {delta_class}">{display}</span>{pct_html}'.format(
        delta_class=delta_class,
        display=escape(display),
        pct_html=pct_html,
    )


def _render_nodecount_compare_table(summary_rows, node_counts, selected_count):
    by_nodes = {
        int(count): [row for row in summary_rows if _to_int(row.get("nodes", 0), 0) == int(count)]
        for count in node_counts
    }
    baseline_count = int(node_counts[0]) if node_counts else None
    previous_counts = [int(count) for count in node_counts if int(count) < int(selected_count)]
    previous_count = previous_counts[-1] if previous_counts else None

    head = ["<th>Metric</th>"]
    for count in node_counts:
        classes = ["col-nodes"]
        if int(count) == int(selected_count):
            classes.append("compare-current")
        head.append('<th class="{classes}">{label}</th>'.format(classes=" ".join(classes), label=escape("{} Nodes".format(int(count)))))
    head.append("<th>{}</th>".format(escape("Δ vs {}".format(previous_count) if previous_count is not None else "Δ vs Smaller")))
    head.append("<th>{}</th>".format(escape("Δ vs {}".format(baseline_count) if baseline_count is not None else "Δ vs First")))

    body = []
    for field in NODECOUNT_COMPARE_FIELDS:
        cells = ['<td class="metric-ink"><strong>{}</strong></td>'.format(escape(_field_label(field)))]
        current_value = _average_for_rows(by_nodes.get(int(selected_count), []), field)
        previous_value = _average_for_rows(by_nodes.get(int(previous_count), []), field) if previous_count is not None else None
        baseline_value = _average_for_rows(by_nodes.get(int(baseline_count), []), field) if baseline_count is not None else None

        for count in node_counts:
            value = _average_for_rows(by_nodes.get(int(count), []), field)
            display = escape(_format_display_value(field, value if value is not None else ""))
            classes = [_cell_class(field, value if value is not None else "")]
            if int(count) == int(selected_count):
                classes.append("compare-current")
            cells.append('<td class="{classes}">{display}</td>'.format(classes=" ".join(filter(None, classes)), display=display))

        cells.append('<td class="metric-ink">{}</td>'.format(_render_nodecount_delta_html(field, current_value, previous_value)))
        if baseline_count is None or int(selected_count) == int(baseline_count):
            cells.append('<td class="metric-ink"><span class="delta-chip delta-flat">n/a</span></td>')
        else:
            cells.append('<td class="metric-ink">{}</td>'.format(_render_nodecount_delta_html(field, current_value, baseline_value)))
        body.append("<tr>{}</tr>".format("".join(cells)))

    return """<section class="panel">
<div class="panel-head">
  <h2>Node Count Comparison</h2>
  <p class="section-note">The selected node count is highlighted. Plus means the metric increased from the reference size and minus means it decreased.</p>
</div>
<div class="table-wrap">
  <table>
    <thead><tr>{head}</tr></thead>
    <tbody>{body}</tbody>
  </table>
</div>
</section>""".format(head="".join(head), body="".join(body))


def _render_nodecount_panel(summary_rows, watch_rows):
    node_counts = sorted({int(_to_int(row.get("nodes", 0), 0)) for row in summary_rows if _to_int(row.get("nodes", 0), 0) > 0})
    if not node_counts:
        return "", ""

    button_html = []
    panels_html = []
    for idx, count in enumerate(node_counts):
        subset = sorted(
            [row for row in summary_rows if _to_int(row.get("nodes", 0), 0) == int(count)],
            key=lambda item: _to_int(item.get("run_index", 0), 0),
        )
        watch_subset = sorted(
            [row for row in watch_rows if _to_int(row.get("nodes", 0), 0) == int(count)],
            key=lambda item: (_to_int(item.get("run_index", 0), 0), str(item.get("view", ""))),
        )
        button_html.append(
            '<button type="button" class="scenario-tab{active}" data-nodecount-tab="{count}">{count} Nodes</button>'.format(
                active=" active" if idx == 0 else "",
                count=int(count),
            )
        )

        avg_mb = _average_for_rows(subset, "total_mb")
        avg_fail = _average_for_rows(subset, "tx_fail_total")
        avg_timeout = _average_for_rows(subset, "tx_timeout_total")
        avg_reachable = _average_for_rows(subset, "reachable_nodes")
        avg_active = _average_for_rows(subset, "active_duration_sec")

        panels_html.append(
            """<div class="nodecount-panel{active}" data-nodecount-panel="{count}">
{cards}
{compare}
{runs}
{watches}
</div>""".format(
                active=" active" if idx == 0 else "",
                count=int(count),
                cards=_render_cards_html(
                    [
                        {
                            "label": "Runs",
                            "value": str(len(subset)),
                            "note": "{} watch rows".format(len(watch_subset)),
                            "tone": "accent",
                        },
                        {
                            "label": "Avg Traffic",
                            "value": _format_display_value("total_mb", avg_mb if avg_mb is not None else 0.0),
                            "note": "average per {}-node run".format(int(count)),
                            "tone": "accent",
                        },
                        {
                            "label": "Avg Failures",
                            "value": _format_display_value("tx_fail_total", avg_fail if avg_fail is not None else 0.0),
                            "note": "{} avg timeouts".format(_format_display_value("tx_timeout_total", avg_timeout if avg_timeout is not None else 0.0)),
                            "tone": "warn" if avg_fail and avg_fail > 0 else "good",
                        },
                        {
                            "label": "Avg Reachable",
                            "value": _format_display_value("reachable_nodes", avg_reachable if avg_reachable is not None else 0.0),
                            "note": "{} active time".format(_format_display_value("active_duration_sec", avg_active if avg_active is not None else 0.0)),
                            "tone": "accent",
                        },
                    ]
                ),
                compare=_render_nodecount_compare_table(summary_rows, node_counts, count),
                runs=_render_table_html(
                    "{}-Node Run Overview".format(int(count)),
                    subset,
                    RUN_OVERVIEW_FIELDS,
                    "Only runs with {} nodes are shown here.".format(int(count)),
                ),
                watches=_render_table_html(
                    "{}-Node Watched Nodes".format(int(count)),
                    watch_subset,
                    WATCH_OVERVIEW_FIELDS,
                    "Only LOCAL and FAR watch rows from {}-node runs are shown here.".format(int(count)),
                ),
            )
        )

    panel_html = """<section class="panel">
<div class="panel-head">
  <h2>Compare 49 vs 64 vs 81</h2>
  <p class="section-note">Pick a node-count tab to filter the run and watch tables below. The comparison table keeps signed plus/minus deltas so scaling changes are easy to see.</p>
</div>
<div class="scenario-tab-row">{buttons}</div>
</section>
{panels}""".format(buttons="".join(button_html), panels="".join(panels_html))

    script_html = """<script>
(() => {{
  const buttons = Array.from(document.querySelectorAll('[data-nodecount-tab]'));
  const panels = Array.from(document.querySelectorAll('[data-nodecount-panel]'));
  if (!buttons.length || !panels.length) return;

  function showTab(value) {{
    buttons.forEach((button) => {{
      button.classList.toggle('active', button.getAttribute('data-nodecount-tab') === value);
    }});
    panels.forEach((panel) => {{
      panel.classList.toggle('active', panel.getAttribute('data-nodecount-panel') === value);
    }});
  }}

  buttons.forEach((button) => {{
    button.addEventListener('click', () => {{
      showTab(button.getAttribute('data-nodecount-tab') || '');
    }});
  }});

  showTab(buttons[0].getAttribute('data-nodecount-tab') || '');
}})();
</script>"""
    return panel_html, script_html


def _render_node_spotlight_panel(evidence, history_rows, watch_ports=None, node_logs=None):
    node_payload = _node_spotlight_payload(evidence, watch_ports=watch_ports)
    if not node_payload:
        return "", ""

    options_html = "".join(
        '<option value="{value}">{label}</option>'.format(value=escape(str(row["port"])), label=escape(str(row.get("summary_label", row["port"]))))
        for row in node_payload
    )
    metric_options_html = "".join(
        '<option value="{value}">{label}</option>'.format(value=escape(field), label=escape(_field_label(field)))
        for field in WATCH_CHART_FIELDS + ["current_missing_count"]
    )
    node_json = escape(json.dumps(node_payload))
    history_json = escape(json.dumps(history_rows or []))
    node_logs_json = escape(json.dumps(node_logs or {}))

    panel_html = """<section class="panel">
<div class="panel-head">
  <h2>Node Spotlight</h2>
  <p class="section-note">Pick any node, or click a row in the watched-node or all-node tables, to inspect its counters, history, and recent messages.</p>
</div>
<div class="spotlight-banner">
  <div>
    <div class="spotlight-banner-label">Selected Node</div>
    <div id="spotlight-selected-title" class="spotlight-banner-title"></div>
    <div id="spotlight-selected-subtitle" class="spotlight-banner-subtitle"></div>
  </div>
  <div id="spotlight-selected-tags" class="spotlight-chip-row"></div>
</div>
<div class="control-row">
  <div class="control-field">
    <label for="spotlight-port-select">Node Port</label>
    <select id="spotlight-port-select">{}</select>
  </div>
  <div class="control-field">
    <label for="spotlight-metric-select">History Metric</label>
    <select id="spotlight-metric-select">{}</select>
  </div>
</div>
<div class="spotlight-chip-row" style="margin-top:12px;">
  <button type="button" class="jump-chip" data-spotlight-jump="LOCAL">Local Watch</button>
  <button type="button" class="jump-chip" data-spotlight-jump="FAR">Far Watch</button>
  <button type="button" class="jump-chip" data-spotlight-jump="BUSIEST">Busiest By Bytes</button>
  <button type="button" class="jump-chip" data-spotlight-jump="QUIETEST">Quietest By Bytes</button>
  <button type="button" class="jump-chip" data-spotlight-jump="MOST_MSGS">Most Accepted Msgs</button>
</div>
<div id="spotlight-cards" class="micro-grid"></div>
<div class="spotlight-grid" style="margin-top:12px;">
  <div class="spotlight-card">
    <h3>Selected Node History</h3>
    <div id="spotlight-point-detail" class="chart-detail">Hover or click a point to inspect its exact sample time and delta.</div>
    <div id="spotlight-chart"></div>
    <p id="spotlight-history-note" class="micro-note">The selected point stays highlighted so you can compare it with the timestamped message activity beside it.</p>
  </div>
  <div class="spotlight-card">
    <h3>Recent Messages (Timestamped)</h3>
    <p class="micro-note">Short in-memory message trail captured from the node state.</p>
    <ul id="spotlight-log" class="spotlight-log"></ul>
  </div>
</div>
<div class="spotlight-grid" style="margin-top:12px;">
  <div class="spotlight-card">
    <h3>Raw Node Log Tail</h3>
    <p id="spotlight-log-context" class="micro-note accent-note">Click a chart point to compare that sample with the raw timestamped node log below.</p>
    <pre id="spotlight-log-tail" class="spotlight-log-tail"></pre>
  </div>
  <div class="spotlight-card">
    <h3>Extra Context</h3>
    <div id="spotlight-extra"></div>
  </div>
</div>
</section>""".format(options_html, metric_options_html)

    script_html = """<script type="application/json" id="spotlight-node-data">{node_json}</script>
<script type="application/json" id="spotlight-history-data">{history_json}</script>
<script type="application/json" id="spotlight-log-data">{node_logs_json}</script>
<script>
(() => {{
  const nodes = JSON.parse(document.getElementById('spotlight-node-data').textContent || '[]');
  const historyRows = JSON.parse(document.getElementById('spotlight-history-data').textContent || '[]');
  const nodeLogs = JSON.parse(document.getElementById('spotlight-log-data').textContent || '{{}}');
  if (!nodes.length) return;
  const portSelect = document.getElementById('spotlight-port-select');
  const metricSelect = document.getElementById('spotlight-metric-select');
  const titleHost = document.getElementById('spotlight-selected-title');
  const subtitleHost = document.getElementById('spotlight-selected-subtitle');
  const tagsHost = document.getElementById('spotlight-selected-tags');
  const cardsHost = document.getElementById('spotlight-cards');
  const pointDetailHost = document.getElementById('spotlight-point-detail');
  const chartHost = document.getElementById('spotlight-chart');
  const noteHost = document.getElementById('spotlight-history-note');
  const logHost = document.getElementById('spotlight-log');
  const logTailHost = document.getElementById('spotlight-log-tail');
  const logContextHost = document.getElementById('spotlight-log-context');
  const extraHost = document.getElementById('spotlight-extra');
  const jumpButtons = Array.from(document.querySelectorAll('[data-spotlight-jump]'));
  const clickableRows = Array.from(document.querySelectorAll('[data-spotlight-port]'));
  const intFmt = new Intl.NumberFormat('en-US');

  function toNum(value) {{
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
  }}

  function fmt(field, value) {{
    if (value === null || value === undefined || Number.isNaN(value)) return 'n/a';
    if (field.endsWith('_mb')) return value.toFixed(3) + ' MB';
    if (field.includes('bytes')) return intFmt.format(Math.round(value));
    if (Math.abs(value - Math.round(value)) < 1e-9) return intFmt.format(Math.round(value));
    return value.toFixed(3);
  }}

  function rankBy(field, port, descending = true) {{
    const ordered = nodes
      .slice()
      .sort((a, b) => {{
        const left = toNum(a[field]) || 0;
        const right = toNum(b[field]) || 0;
        return descending ? right - left : left - right;
      }});
    const idx = ordered.findIndex(item => String(item.port) === String(port));
    return idx >= 0 ? idx + 1 : null;
  }}

  function averageOf(field) {{
    const values = nodes.map(item => toNum(item[field])).filter(value => value !== null);
    if (!values.length) return null;
    return values.reduce((acc, value) => acc + value, 0) / values.length;
  }}

  function lineSvg(points, color) {{
    if (!points.length) return '<div class="chart-empty">No sampled history for this node in the current run.</div>';
    const width = 360;
    const height = 150;
    const padX = 14;
    const padTop = 14;
    const padBottom = 22;
    const values = points.map(point => point.value);
    let min = Math.min(...values);
    let max = Math.max(...values);
    if (Math.abs(max - min) < 1e-9) max = min + 1;
    const usableW = width - padX * 2;
    const usableH = height - padTop - padBottom - 10;
    const stepX = points.length > 1 ? usableW / (points.length - 1) : 0;
    const coords = points.map((point, idx) => {{
      const x = points.length > 1 ? padX + idx * stepX : padX + usableW / 2;
      const ratio = (point.value - min) / (max - min);
      const y = padTop + (1 - ratio) * usableH;
      const prev = idx > 0 ? points[idx - 1].value : null;
      return {{ x, y, point, delta: prev === null ? null : point.value - prev }};
    }});
    const polyline = coords.map(point => `${{point.x.toFixed(2)}},${{point.y.toFixed(2)}}`).join(' ');
    const fillPoly = [`${{coords[0].x.toFixed(2)}},${{(height - padBottom).toFixed(2)}}`]
      .concat(coords.map(point => `${{point.x.toFixed(2)}},${{point.y.toFixed(2)}}`))
      .concat([`${{coords[coords.length - 1].x.toFixed(2)}},${{(height - padBottom).toFixed(2)}}`])
      .join(' ');
    const circles = coords.map(point => {{
      const deltaValue = point.delta === null ? '' : point.delta.toFixed(3);
      const deltaDisplay = point.delta === null ? 'start' : `${{point.delta > 0 ? '+' : ''}}${{point.delta.toFixed(3)}}`;
      return `<circle cx="${{point.x.toFixed(2)}}" cy="${{point.y.toFixed(2)}}" r="3.2" fill="${{color}}" class="chart-point" tabindex="0" data-label="${{point.point.label}}" data-value="${{point.point.value.toFixed(3)}}" data-delta="${{deltaValue}}" data-value-display="${{fmt(metricSelect.value || 'pull_rx', point.point.value)}}" data-delta-display="${{deltaDisplay}}"><title>${{point.point.label}} | ${{
fmt(metricSelect.value || 'pull_rx', point.point.value)
}} | delta ${{deltaDisplay}}</title></circle>`;
    }}).join('');
    return `<svg viewBox="0 0 ${{width}} ${{height}}" class="metric-chart" role="img" aria-label="metric chart">
      <line x1="${{padX}}" y1="${{height - padBottom}}" x2="${{width - padX}}" y2="${{height - padBottom}}" class="chart-axis"></line>
      <line x1="${{padX}}" y1="${{padTop}}" x2="${{padX}}" y2="${{height - padBottom}}" class="chart-axis"></line>
      <polygon points="${{fillPoly}}" fill="${{color}}" opacity="0.12"></polygon>
      <polyline points="${{polyline}}" fill="none" stroke="${{color}}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>
      ${{circles}}
    </svg>`;
  }}

  function bindChartDetail() {{
    const points = Array.from(chartHost.querySelectorAll('.chart-point'));
    if (!points.length) {{
      pointDetailHost.textContent = 'No sampled history exists for this node in this run.';
      if (logContextHost) {{
        logContextHost.textContent = 'Raw node log is still shown below, but this run did not capture sampled history for the selected node.';
      }}
      return;
    }}
    const update = (point) => {{
      points.forEach((item) => item.classList.toggle('is-active', item === point));
      const label = point.getAttribute('data-label') || '';
      const value = point.getAttribute('data-value-display') || point.getAttribute('data-value') || '';
      const delta = point.getAttribute('data-delta-display') || 'n/a';
      pointDetailHost.innerHTML = `<strong>${{label}}</strong> · value ${{value}} · delta ${{delta}}`;
      if (logContextHost) {{
        logContextHost.textContent = `Selected sample ${{label}}. Compare this chart point with the raw timestamped node log below.`;
      }}
    }};
    points.forEach((point) => {{
      point.addEventListener('mouseenter', () => update(point));
      point.addEventListener('focus', () => update(point));
      point.addEventListener('click', () => update(point));
    }});
    update(points[points.length - 1]);
  }}

  function setSelectedPort(port) {{
    if (!port) return;
    portSelect.value = String(port);
    render();
  }}

  function render() {{
    const fallbackNode = nodes.find(item => String(item.watch_role) === 'LOCAL') || nodes[0];
    const port = String(portSelect.value || fallbackNode.port);
    const metric = metricSelect.value || 'pull_rx';
    const node = nodes.find(item => String(item.port) === port) || nodes[0];
    const history = historyRows
      .filter(item => String(item.port) === port)
      .sort((a, b) => (toNum(a.sample_index) || 0) - (toNum(b.sample_index) || 0))
      .map(item => ({{ label: String(item.sample_label || ''), value: toNum(item[metric]) }}))
      .filter(item => item.value !== null);
    const nodeLogLines = Array.isArray(nodeLogs[port]) ? nodeLogs[port] : [];
    const avgBytes = averageOf('total_bytes');
    const avgAccepted = averageOf('accepted_messages');
    const bytesRank = rankBy('total_bytes', port, true);
    const acceptedRank = rankBy('accepted_messages', port, true);
    const watchRole = String(node.watch_role || '').trim();
    const roleText = watchRole ? `${{watchRole}} watch` : 'Regular node';
    const sampleCount = history.length;
    const historyLatest = history.length ? history[history.length - 1].value : null;
    const tags = [
      watchRole ? `${{watchRole}} WATCH` : 'REGULAR',
      node.reachable ? 'REACHABLE' : 'UNREACHABLE',
      `Traffic rank #${{bytesRank || 'n/a'}}`,
      `Msg rank #${{acceptedRank || 'n/a'}}`,
    ];

    titleHost.textContent = `Port ${{port}}`;
    subtitleHost.textContent = `${{roleText}} · ${{node.protocol_state || 'UNKNOWN'}} · ${{fmt('total_mb', toNum(node.total_mb))}} traffic · ${{sampleCount}} history samples`;
    tagsHost.innerHTML = tags.map(tag => `<span class="badge pill-soft">${{tag}}</span>`).join('');

    const cards = [
      {{ label: 'Role', value: watchRole || 'REGULAR', note: watchRole ? 'watched node in the paper report' : 'ordinary node' }},
      {{ label: 'State', value: node.protocol_state || 'UNKNOWN', note: node.boundary_kind || 'no boundary label' }},
      {{ label: 'Traffic Rank', value: bytesRank ? `#${{bytesRank}} / ${{nodes.length}}` : 'n/a', note: 'ranked by total bytes among all nodes' }},
      {{ label: 'Accepted Rank', value: acceptedRank ? `#${{acceptedRank}} / ${{nodes.length}}` : 'n/a', note: 'ranked by accepted messages among all nodes' }},
      {{ label: 'Traffic', value: fmt('total_mb', toNum(node.total_mb)), note: fmt('total_bytes', toNum(node.total_bytes)) + ' total bytes' }},
      {{ label: 'Vs Avg Traffic', value: avgBytes === null ? 'n/a' : fmt('total_bytes', (toNum(node.total_bytes) || 0) - avgBytes), note: 'difference from network average bytes' }},
      {{ label: 'Accepted Msgs', value: fmt('accepted_messages', toNum(node.accepted_messages)), note: avgAccepted === null ? 'messages accepted by the node' : `network avg ${{
fmt('accepted_messages', avgAccepted)
}}` }},
      {{ label: 'Pull RX', value: fmt('pull_rx', toNum(node.pull_rx)), note: 'inbound pull requests served' }},
      {{ label: 'Pull TX', value: fmt('pull_tx', toNum(node.pull_tx)), note: 'outbound pull requests sent' }},
      {{ label: 'Push RX', value: fmt('push_rx', toNum(node.push_rx)), note: 'protocol push messages received' }},
      {{ label: 'Push TX', value: fmt('push_tx', toNum(node.push_tx)), note: 'protocol push messages sent' }},
      {{ label: 'Missing Neighbors', value: fmt('current_missing_count', toNum(node.current_missing_count)), note: 'current missing-neighbor count' }},
    ];
    cardsHost.innerHTML = cards.map(card => `<div class="micro-card"><div class="micro-label">${{card.label}}</div><div class="micro-value">${{card.value}}</div><div class="micro-note">${{card.note}}</div></div>`).join('');

    chartHost.innerHTML = lineSvg(history, '#118a7e');
    bindChartDetail();
    noteHost.textContent = history.length
      ? `Tracking ${{metric.replaceAll('_', ' ')}} for port ${{port}} across sampled pull history. Latest value: ${{fmt(metric, historyLatest)}}.`
      : 'No sampled history exists for this node in this run. New runs after the history patch will fill this in.';

    const recentMsgs = Array.isArray(node.recent_msgs) && node.recent_msgs.length ? node.recent_msgs : ['No recent messages captured.'];
    logHost.innerHTML = recentMsgs.map(item => `<li>${{item}}</li>`).join('');
    logTailHost.textContent = nodeLogLines.length
      ? nodeLogLines.join('\\n')
      : 'No raw node log was captured for this node in this run.';
    if (!history.length && logContextHost) {{
      logContextHost.textContent = `Showing the raw node log tail for port ${{port}}. This run did not capture sampled history for the selected node.`;
    }}
    extraHost.innerHTML = `
      <div class="micro-grid">
        <div class="micro-card"><div class="micro-label">Phase</div><div class="micro-value">${{node.phase || 'n/a'}}</div><div class="micro-note">layer-2 phase or check-in phase</div></div>
        <div class="micro-card"><div class="micro-label">Direction</div><div class="micro-value">${{node.direction_label || 'n/a'}}</div><div class="micro-note">direction label when available</div></div>
        <div class="micro-card"><div class="micro-label">Pull Cycles</div><div class="micro-value">${{fmt('pull_cycles', toNum(node.pull_cycles))}}</div><div class="micro-note">local pull loop iterations</div></div>
        <div class="micro-card"><div class="micro-label">Known Nodes</div><div class="micro-value">${{fmt('known_nodes_count', toNum(node.known_nodes_count))}}</div><div class="micro-note">known-neighbor count</div></div>
        <div class="micro-card"><div class="micro-label">Incoming Events</div><div class="micro-value">${{fmt('incoming_events_count', toNum(node.incoming_events_count))}}</div><div class="micro-note">recent inbound event count</div></div>
        <div class="micro-card"><div class="micro-label">Fault Flags</div><div class="micro-value">${{node.crash_sim || node.lie_sensor || node.flap ? 'ACTIVE' : 'OFF'}}</div><div class="micro-note">crash=${{node.crash_sim ? 'on' : 'off'}}, lie=${{node.lie_sensor ? 'on' : 'off'}}, flap=${{node.flap ? 'on' : 'off'}}</div></div>
      </div>
      <p class="micro-note" style="margin-top:12px;">Recent alerts: ${{Array.isArray(node.recent_alerts) && node.recent_alerts.length ? node.recent_alerts.join(', ') : 'none captured'}}</p>
    `;

    clickableRows.forEach((row) => {{
      row.classList.toggle('row-selected', String(row.getAttribute('data-spotlight-port') || '') === port);
    }});
  }}

  jumpButtons.forEach((button) => {{
    const kind = button.getAttribute('data-spotlight-jump') || '';
    let target = null;
    if (kind === 'LOCAL') target = (nodes.find(item => String(item.watch_role) === 'LOCAL') || {{}}).port;
    if (kind === 'FAR') target = (nodes.find(item => String(item.watch_role) === 'FAR') || {{}}).port;
    if (kind === 'BUSIEST') target = (nodes.slice().sort((a, b) => (toNum(b.total_bytes) || 0) - (toNum(a.total_bytes) || 0))[0] || {{}}).port;
    if (kind === 'QUIETEST') target = (nodes.slice().sort((a, b) => (toNum(a.total_bytes) || 0) - (toNum(b.total_bytes) || 0))[0] || {{}}).port;
    if (kind === 'MOST_MSGS') target = (nodes.slice().sort((a, b) => (toNum(b.accepted_messages) || 0) - (toNum(a.accepted_messages) || 0))[0] || {{}}).port;
    if (!target) {{
      button.disabled = true;
      return;
    }}
    button.addEventListener('click', () => setSelectedPort(target));
  }});

  clickableRows.forEach((row) => {{
    row.addEventListener('click', () => setSelectedPort(row.getAttribute('data-spotlight-port')));
    row.addEventListener('keydown', (event) => {{
      if (event.key === 'Enter' || event.key === ' ') {{
        event.preventDefault();
        setSelectedPort(row.getAttribute('data-spotlight-port'));
      }}
    }});
  }});

  portSelect.addEventListener('change', render);
  metricSelect.addEventListener('change', render);
  const defaultNode = nodes.find(item => String(item.watch_role) === 'LOCAL') || nodes[0];
  portSelect.value = String(defaultNode.port);
  render();
}})();
</script>""".format(node_json=node_json, history_json=history_json, node_logs_json=node_logs_json)
    return panel_html, script_html


def _write_run_html(run_dir, manifest, summary_row, watch_rows, evidence, events_path, history_rows=None, history_totals_rows=None, timeline_rows=None, fire_stage_rows=None, figure_links=None):
    history_rows = history_rows or []
    history_totals_rows = history_totals_rows or []
    timeline_rows = timeline_rows or []
    fire_stage_rows = fire_stage_rows or []
    figure_links = figure_links or []
    node_rows = _all_node_rows(evidence)
    node_logs = _node_log_tails(run_dir, [row.get("port") for row in node_rows], max_lines=36)
    watch_ports = manifest.get("watch_ports", {})
    local_port = int(watch_ports.get("LOCAL", 0)) if watch_ports.get("LOCAL") is not None else None
    far_port = int(watch_ports.get("FAR", 0)) if watch_ports.get("FAR") is not None else None
    local_history = [row for row in history_rows if local_port is not None and _to_int(row.get("port", -1), -1) == int(local_port)]
    far_history = [row for row in history_rows if far_port is not None and _to_int(row.get("port", -1), -1) == int(far_port)]
    spotlight_html, spotlight_script = _render_node_spotlight_panel(evidence, history_rows, watch_ports=watch_ports, node_logs=node_logs)

    cards = [
        {
            "label": "Status",
            "value": _format_display_value("status", summary_row.get("status", "")),
            "note": "{} nodes".format(_format_display_value("nodes", summary_row.get("nodes", ""))),
            "tone": "good" if str(summary_row.get("status", "")).strip().lower() == "ok" else "bad",
        },
        {
            "label": "Traffic",
            "value": _format_display_value("total_mb", summary_row.get("total_mb", 0.0)),
            "note": "{} total bytes".format(_format_display_value("total_bytes", summary_row.get("total_bytes", 0))),
            "tone": "accent",
        },
        {
            "label": "Events",
            "value": _format_display_value("events_total", summary_row.get("events_total", 0)),
            "note": "{} trigger ops".format(_format_display_value("trigger_ops", summary_row.get("trigger_ops", 0))),
            "tone": "accent",
        },
        {
            "label": "Detection",
            "value": _format_display_value("detection_speed_sec", summary_row.get("detection_speed_sec", "")) or "n/a",
            "note": "LOCAL watch first saw the scenario here",
            "tone": "accent" if _maybe_float(summary_row.get("detection_speed_sec")) is not None else "warn",
        },
        {
            "label": "Failures",
            "value": _format_display_value("tx_fail_total", summary_row.get("tx_fail_total", 0)),
            "note": "{} timeouts, {} conn errors".format(
                _format_display_value("tx_timeout_total", summary_row.get("tx_timeout_total", 0)),
                _format_display_value("tx_conn_error_total", summary_row.get("tx_conn_error_total", 0)),
            ),
            "tone": "bad" if _maybe_float(summary_row.get("tx_fail_total", 0)) else "good",
        },
        {
            "label": "Residual Risk",
            "value": "{} / {}".format(
                _format_display_value("false_positive_nodes", summary_row.get("false_positive_nodes", 0)),
                _format_display_value("false_unavailable_refs", summary_row.get("false_unavailable_refs", 0)),
            ),
            "note": "false positives / false unavailable refs",
            "tone": "bad" if _to_int(summary_row.get("false_positive_nodes", 0), 0) or _to_int(summary_row.get("false_unavailable_refs", 0), 0) else "good",
        },
    ]

    sections = [
        _render_glossary_html(),
        _render_field_reference_html(),
        _render_timeline_panel(timeline_rows),
        _render_fire_semantics_panel(fire_stage_rows),
        _render_table_html("Run Overview", [summary_row], RUN_OVERVIEW_FIELDS, "Color badges make the health signals easier to spot at a glance."),
        _render_spotlight_table_html("Watched Nodes", watch_rows, WATCH_OVERVIEW_FIELDS, "watch_port", "Local rows are warm-toned, far rows are cool-toned. Click a row to sync Node Spotlight."),
        spotlight_html,
        _render_chart_grid_html(
            "Pull History",
            history_totals_rows,
            ["pull_rx_total", "pull_tx_total", "push_rx_total", "push_tx_total", "accepted_messages_total", "total_mb"],
            _sample_label,
            "These sampled totals show how traffic and accepted messages evolve during the run.",
        ),
        _render_chart_grid_html(
            "Local Watch History",
            local_history,
            WATCH_CHART_FIELDS,
            _sample_label,
            "This follows the local watch node over time.",
        ),
        _render_chart_grid_html(
            "Far Watch History",
            far_history,
            WATCH_CHART_FIELDS,
            _sample_label,
            "This follows the far watch node over time.",
        ),
        _render_spotlight_table_html("All Nodes Snapshot", node_rows, NODE_FIELDS, "port", "Every node at the end of the run, so you can spot hotspots and outliers quickly. Click any row to inspect it above."),
        _render_links_html(
            "Raw Files",
            [
                ("paper_summary.tsv", "paper_summary.tsv"),
                ("paper_watch_nodes.tsv", "paper_watch_nodes.tsv"),
                ("paper_all_nodes.tsv", "paper_all_nodes.tsv"),
                ("paper_pull_history.tsv", "paper_pull_history.tsv"),
                ("paper_pull_totals.tsv", "paper_pull_totals.tsv"),
                ("paper_timeline.tsv", "paper_timeline.tsv"),
                ("paper_fire_stages.tsv", "paper_fire_stages.tsv"),
                ("paper_summary.md", "paper_summary.md"),
                ("paper_manifest.json", "paper_manifest.json"),
                ("paper_evidence.json", "paper_evidence.json"),
                (Path(events_path).name, Path(events_path).name),
            ] + figure_links,
        ),
        "<details><summary>Show Timeline Table</summary>{}</details>".format(
            _render_table_html("Timeline", timeline_rows, TIMELINE_FIELDS)
        ),
        (
            "<details><summary>Show Fire Stage Table</summary>{}</details>".format(
                _render_table_html("Fire Stages", fire_stage_rows, FIRE_STAGE_FIELDS)
            )
            if fire_stage_rows
            else ""
        ),
        "<details><summary>Show Pull Totals Table</summary>{}</details>".format(
            _render_table_html("Pull Totals Over Time", history_totals_rows, HISTORY_TOTAL_FIELDS)
        ),
        "<details><summary>Show Pull History Table</summary>{}</details>".format(
            _render_table_html("All Sampled Pull Rows", history_rows, HISTORY_FIELDS)
        ),
        "<details><summary>Show Full Summary Row</summary>{}</details>".format(
            _render_table_html("Full Summary Fields", [summary_row], SUMMARY_FIELDS)
        ),
        "<details><summary>Show Full Watch Rows</summary>{}</details>".format(
            _render_table_html("Full Watch Fields", watch_rows, WATCH_FIELDS)
        ),
    ]

    subtitle = "{} | {} | Run {} Seed {}".format(
        manifest.get("phase_name", "Paper Evaluation Run"),
        summary_row.get("challenge", ""),
        summary_row.get("run_index", ""),
        summary_row.get("seed", ""),
    )
    _write_text(run_dir / "paper_summary.html", _html_page("Paper Evaluation Run", subtitle, _render_cards_html(cards), "".join(sections), script_html=spotlight_script))


def _write_suite_html(report_dir, spec, summary_rows, watch_rows, summary_by_nodes_rows, figure_links=None):
    figure_links = figure_links or []
    total_runs = len(summary_rows)
    total_mb_values = [float(row.get("total_mb", 0.0)) for row in summary_rows]
    total_failures = sum(int(row.get("tx_fail_total", 0)) for row in summary_rows)
    ok_runs = sum(1 for row in summary_rows if str(row.get("status", "")).strip().lower() == "ok")
    accuracy_values = [_maybe_float(row.get("settle_accuracy_pct")) for row in summary_rows]
    accuracy_values = [float(value) for value in accuracy_values if value is not None]
    summary_metric_rows = _metric_summary_rows(summary_rows, SUMMARY_CHART_FIELDS)
    interactive_html, interactive_script = _render_suite_interactive_panel(summary_rows)
    nodecount_html, nodecount_script = _render_nodecount_panel(summary_rows, watch_rows)
    comparison_rows = _build_protocol_comparison_rows()
    comparison_html, comparison_script = _render_comparison_panel(comparison_rows)
    cards = [
        {
            "label": "Protocol",
            "value": str(spec.get("protocol", "")).upper(),
            "note": str(spec.get("phase_name", "")),
            "tone": "accent",
        },
        {
            "label": "Runs",
            "value": str(total_runs),
            "note": "{} node settings".format(len({int(row.get("nodes", 0)) for row in summary_rows})),
            "tone": "accent",
        },
        {
            "label": "Avg Traffic",
            "value": "{:.3f} MB".format(statistics.mean(total_mb_values)) if total_mb_values else "0.000 MB",
            "note": "per run",
            "tone": "accent",
        },
        {
            "label": "Healthy Runs",
            "value": "{}/{}".format(ok_runs, total_runs),
            "note": "{} TX failures".format(total_failures),
            "tone": "good" if total_failures == 0 else "warn",
        },
        {
            "label": "Settle Accuracy",
            "value": "{:.1f}%".format(statistics.mean(accuracy_values)) if accuracy_values else "n/a",
            "note": "final normal-state accuracy across runs",
            "tone": "good" if accuracy_values and statistics.mean(accuracy_values) >= 95.0 else "warn",
        },
    ]

    sections = [
        _render_glossary_html(),
        _render_field_reference_html(),
        interactive_html,
        nodecount_html,
        comparison_html,
        _render_run_deep_dive_html(report_dir, summary_rows),
        _render_table_html("Run Overview", summary_rows, RUN_OVERVIEW_FIELDS, "This is the quickest table to compare one run against another."),
        _render_chart_grid_html(
            "Run Metric Charts",
            summary_rows,
            SUMMARY_CHART_FIELDS,
            _run_label,
            "Each chart tracks one metric across the saved runs, which is useful when you do the full 30-run suite.",
        ),
        _render_table_html("Run Metric Averages", summary_metric_rows, ["metric", "samples", "avg", "min", "max", "latest"], "Quick average/min/max table for the suite metrics."),
        _render_table_html("Watched Nodes", watch_rows, WATCH_OVERVIEW_FIELDS, "Use this for per-node load, state, and fault visibility."),
        _render_table_html("Grouped By Node Count", summary_by_nodes_rows, SUMMARY_BY_NODES_FIELDS, "A compact roll-up for 49 vs 64 vs 81 style comparisons."),
        _render_links_html(
            "Raw Files",
            [
                ("all_runs.tsv", "all_runs.tsv"),
                ("all_watch_nodes.tsv", "all_watch_nodes.tsv"),
                ("summary_by_nodes.tsv", "summary_by_nodes.tsv"),
                ("metric_averages.tsv", "metric_averages.tsv"),
                ("protocol_comparison.tsv", "protocol_comparison.tsv"),
                ("README.md", "README.md"),
            ] + figure_links,
        ),
        "<details><summary>Show Full Run Table</summary>{}</details>".format(
            _render_table_html("All Run Fields", summary_rows, SUMMARY_FIELDS)
        ),
        "<details><summary>Show Full Watch Table</summary>{}</details>".format(
            _render_table_html("All Watch Fields", watch_rows, WATCH_FIELDS)
        ),
    ]

    subtitle = "{} | {} | {} second window".format(
        spec.get("phase_name", "Paper Evaluation Suite"),
        spec.get("challenge", ""),
        spec.get("duration_sec", ""),
    )
    _write_text(
        report_dir / "index.html",
        _html_page(
            "Paper Evaluation Dashboard",
            subtitle,
            _render_cards_html(cards),
            "".join(sections),
            script_html=(interactive_script + nodecount_script + comparison_script),
        ),
    )


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


def _fire_ignition_port(base_port, number_of_nodes):
    return _center_port(base_port, number_of_nodes)


def _fire_core_ports(base_port, number_of_nodes):
    ignition = _fire_ignition_port(base_port, number_of_nodes)
    core = [int(ignition)]
    for neighbor in _neighbors_for_port(base_port, number_of_nodes, ignition):
        if int(neighbor) not in core:
            core.append(int(neighbor))
        if len(core) >= 3:
            break
    return sorted(core)


def _fire_spread_batches(base_port, number_of_nodes):
    ignition = _fire_ignition_port(base_port, number_of_nodes)
    visited = {int(ignition)}
    frontier = [int(ignition)]
    layers = []

    while frontier:
        layers.append(sorted(int(port) for port in frontier))
        next_frontier = []
        for port in frontier:
            for neighbor in _neighbors_for_port(base_port, number_of_nodes, port):
                if int(neighbor) in visited:
                    continue
                visited.add(int(neighbor))
                next_frontier.append(int(neighbor))
        frontier = sorted(set(next_frontier))

    return layers


def _fire_actions(spec, base_port, number_of_nodes, seed):
    del seed
    duration_sec = _to_float(spec.get("duration_sec", 60), 60.0)
    spread_batches = _fire_spread_batches(base_port, number_of_nodes)
    core_ports = _fire_core_ports(base_port, number_of_nodes)
    if len(spread_batches) == 0:
        return []
    spread_start = max(2.0, float(duration_sec) * 0.08)
    spread_window = max(6.0, float(duration_sec) * 0.56)
    step_gap = spread_window / max(1, len(spread_batches) - 1) if len(spread_batches) > 1 else spread_window
    recovery_lag = max(step_gap * 1.6, float(duration_sec) * 0.14)
    impacted_ports = sorted({int(port) for batch in spread_batches for port in batch} | {int(port) for port in core_ports})
    actions = []

    for idx, ports in enumerate(spread_batches):
        fire_at = round(spread_start + (idx * step_gap), 3)
        actions.append(
            {
                "at_sec": fire_at,
                "kind": "state_batch",
                "ports": [int(port) for port in ports],
                "sensor_state": "ALERT",
                "label": "fire_front_step_{}".format(idx + 1),
            }
        )
        recover_at = spread_start + (idx * step_gap) + recovery_lag
        if recover_at < float(duration_sec) * 0.90:
            actions.append(
                {
                    "at_sec": round(recover_at, 3),
                    "kind": "state_batch",
                    "ports": [int(port) for port in ports],
                    "sensor_state": "RECOVERING",
                    "label": "fire_recover_step_{}".format(idx + 1),
                }
            )

    bomb_at = min(float(duration_sec) * 0.58, spread_start + (step_gap * max(1, min(2, len(spread_batches) - 1))))
    bomb_recover_at = min(float(duration_sec) * 0.82, bomb_at + max(3.0, step_gap * 1.5))
    reset_at = min(float(duration_sec) - 0.2, max(bomb_recover_at + 1.0, float(duration_sec) * 0.95))
    actions.extend(
        [
            {
                "at_sec": round(bomb_at, 3),
                "kind": "crash_batch",
                "ports": [int(port) for port in core_ports],
                "label": "bomb_core_impact",
            },
            {
                "at_sec": round(bomb_recover_at, 3),
                "kind": "recover_batch",
                "ports": [int(port) for port in core_ports],
                "label": "bomb_core_recover",
            },
            {
                "at_sec": round(reset_at, 3),
                "kind": "reset_batch",
                "ports": impacted_ports,
                "label": "fire_reset",
            },
        ]
    )
    return actions


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
    if kind == "firebomb":
        return _fire_actions(spec, base_port, number_of_nodes, seed)
    if kind == "tornado_sweep":
        return _tornado_actions(spec, base_port, number_of_nodes, seed)
    if kind == "ghost_outage_noise":
        return _stress_actions(spec, base_port, number_of_nodes, seed)
    raise ValueError("unsupported scenario kind: {}".format(kind))


def _watch_ports(spec, base_port, number_of_nodes, seed):
    kind = str(spec.get("scenario", {}).get("kind", "baseline")).strip().lower()
    if kind == "firebomb":
        local_watch = _fire_ignition_port(base_port, number_of_nodes)
    elif kind == "tornado_sweep":
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
    at_sec = round(_to_float(action.get("at_sec", 0.0), 0.0), 3)

    if kind == "crash_batch":
        for port in action.get("ports", []):
            res = _inject_fault(port, "crash_sim", True, period_sec=action.get("period_sec", 4))
            _log_event(events_path, "fault", {"label": label, "port": int(port), "fault": "crash_sim", "enable": True, "response": res, "at_sec": at_sec})
        return

    if kind == "recover_batch":
        for port in action.get("ports", []):
            res_fault = _inject_fault(port, "crash_sim", False, period_sec=action.get("period_sec", 4))
            res_state = _inject_state(port, "RECOVERING")
            _log_event(events_path, "fault", {"label": label, "port": int(port), "fault": "crash_sim", "enable": False, "response": res_fault, "at_sec": at_sec})
            _log_event(events_path, "state", {"label": label, "port": int(port), "sensor_state": "RECOVERING", "response": res_state, "at_sec": at_sec})
        return

    if kind == "reset_batch":
        for port in action.get("ports", []):
            res_reset = _inject_fault(port, "reset", True, period_sec=action.get("period_sec", 4))
            res_state = _inject_state(port, "NORMAL")
            _log_event(events_path, "fault", {"label": label, "port": int(port), "fault": "reset", "enable": True, "response": res_reset, "at_sec": at_sec})
            _log_event(events_path, "state", {"label": label, "port": int(port), "sensor_state": "NORMAL", "response": res_state, "at_sec": at_sec})
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
                "at_sec": at_sec,
            },
        )
        return

    if kind == "state_batch":
        for port in action.get("ports", []):
            res = _inject_state(port, action.get("sensor_state", "NORMAL"))
            _log_event(events_path, "state", {"label": label, "port": int(port), "sensor_state": str(action.get("sensor_state", "NORMAL")), "response": res, "at_sec": at_sec})
        return

    raise ValueError("unsupported action kind: {}".format(kind))


def _run_active_window(spec, base_port, number_of_nodes, run_index, seed, events_path, history_path=None, history_totals_path=None):
    duration_sec = _to_float(spec.get("duration_sec", 60), 60.0)
    trigger_interval_sec = max(0.25, _to_float(spec.get("trigger_interval_sec", 2), 2.0))
    sample_interval_sec = max(0.5, _to_float(spec.get("sample_interval_sec", 1.0), 1.0))
    ports = list(range(int(base_port), int(base_port) + int(number_of_nodes)))
    actions = sorted(_scenario_actions(spec, base_port, number_of_nodes, seed), key=lambda item: float(item.get("at_sec", 0.0)))

    start = time.monotonic()
    deadline = start + float(duration_sec)
    next_trigger = start
    next_sample = start
    trigger_index = 0
    sample_index = 0
    action_index = 0

    _log_event(events_path, "stage", {"name": "active_window_start", "duration_sec": duration_sec, "at_sec": 0.0})

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
                _log_event(events_path, "trigger", {"port": int(port), "label": label, "ok": ok, "response": res, "at_sec": round(float(elapsed), 3)})
            except Exception as exc:
                _log_event(events_path, "trigger_error", {"port": int(port), "label": label, "error": str(exc), "at_sec": round(float(elapsed), 3)})
            trigger_index += 1
            next_trigger += float(trigger_interval_sec)

        if history_path is not None and history_totals_path is not None and now >= next_sample:
            history_rows, totals_row = _sample_nodes(base_port, number_of_nodes, sample_index, now - start)
            for row in history_rows:
                _append_jsonl(history_path, row)
            _append_jsonl(history_totals_path, totals_row)
            sample_index += 1
            next_sample += float(sample_interval_sec)

        remaining = max(0.0, deadline - time.monotonic())
        time.sleep(min(0.05, remaining if remaining > 0.0 else 0.0))

    active_duration_sec = round(float(time.monotonic() - start), 3)

    _log_event(events_path, "done", {"active_duration_sec": active_duration_sec, "trigger_count": int(trigger_index), "at_sec": active_duration_sec})
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
    false_positive_nodes = 0
    false_unavailable_refs = 0

    for port in range(int(base_port), int(base_port) + int(number_of_nodes)):
        try:
            res = _pull_state(port, origin="paper_report", timeout=1.0)
            state = res.get("data", {}).get("node_state", {}) if isinstance(res, dict) else {}
            counters = state.get("msg_counters", {})
            if not isinstance(counters, dict):
                counters = {}
            for key in totals:
                totals[key] += _to_int(counters.get(key, 0), 0)
            false_positive_flag = _false_positive_flag_from_state(state)
            false_unavailable_count = _false_unavailable_refs_from_state(state)
            false_positive_nodes += int(false_positive_flag)
            false_unavailable_refs += int(false_unavailable_count)
            nodes[str(port)] = {
                "reachable": True,
                "state": state,
                "msg_counters": counters,
                "derived": {
                    "false_positive_flag": int(false_positive_flag),
                    "false_unavailable_refs": int(false_unavailable_count),
                },
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
                "protocol_state": _resolved_protocol_state_from_state(state),
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
                "phase": _resolved_phase_from_state(state),
                "distance_hops": _to_float(layer2.get("distance_hops", 99.0), 99.0),
                "eta_cycles": _to_float(layer2.get("eta_cycles", 99.0), 99.0),
                "current_missing_count": _false_unavailable_refs_from_state(state),
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
        "detection_speed_sec": "",
        "first_watch_sec": "",
        "first_impact_sec": "",
        "outage_sec": "",
        "recovery_sec": "",
        "reset_sec": "",
        "false_positive_nodes": int(false_positive_nodes),
        "false_unavailable_refs": int(false_unavailable_refs),
        "settle_accuracy_pct": round(100.0 * max(0.0, 1.0 - (float(false_positive_nodes) / max(1, int(number_of_nodes)))), 1),
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
        "scenario_kind": str(spec.get("scenario", {}).get("kind", "")).strip().lower(),
        "spec_path": str(spec.get("_spec_path", "")),
    }

    return manifest, summary_row, watch_rows, {"nodes": nodes, "totals": totals, "event_counts": event_counts}


def _write_run_reports(run_dir, manifest, summary_row, watch_rows, evidence, events_path, history_path=None, history_totals_path=None):
    manifest_path = run_dir / "paper_manifest.json"
    summary_tsv_path = run_dir / "paper_summary.tsv"
    watch_tsv_path = run_dir / "paper_watch_nodes.tsv"
    all_nodes_tsv_path = run_dir / "paper_all_nodes.tsv"
    history_tsv_path = run_dir / "paper_pull_history.tsv"
    history_totals_tsv_path = run_dir / "paper_pull_totals.tsv"
    timeline_tsv_path = run_dir / "paper_timeline.tsv"
    fire_stage_tsv_path = run_dir / "paper_fire_stages.tsv"
    evidence_path = run_dir / "paper_evidence.json"
    summary_md_path = run_dir / "paper_summary.md"
    history_rows = _load_jsonl(history_path) if history_path else []
    history_totals_rows = _load_jsonl(history_totals_path) if history_totals_path else []
    events_rows = _load_jsonl(events_path)
    node_rows = _all_node_rows(evidence)
    timeline_rows, timeline_metrics = _derive_run_timeline(
        spec={"scenario": {"kind": manifest.get("scenario_kind", "")}},
        manifest=manifest,
        history_rows=history_rows,
        events_rows=events_rows,
    )
    fire_stage_rows = _fire_stage_rows(events_rows) if str(manifest.get("scenario_kind", "")).strip().lower() == "firebomb" else []
    local_port = _to_int(manifest.get("watch_ports", {}).get("LOCAL", 0), 0)
    far_port = _to_int(manifest.get("watch_ports", {}).get("FAR", 0), 0)
    local_history = _history_rows_for_port(history_rows, local_port) if local_port > 0 else []
    far_history = _history_rows_for_port(history_rows, far_port) if far_port > 0 else []
    summary_row.update(timeline_metrics)
    summary_row["settle_accuracy_pct"] = round(100.0 * max(0.0, 1.0 - (_to_float(summary_row.get("false_positive_nodes", 0), 0.0) / max(1, _to_int(summary_row.get("total_nodes", 1), 1)))), 1)
    evidence["timeline"] = timeline_rows
    evidence["fire_stages"] = fire_stage_rows
    figure_links = _write_run_figure_exports(run_dir, history_totals_rows, local_history, far_history, timeline_rows)

    _write_json(manifest_path, manifest)
    _write_json(evidence_path, evidence)
    _write_tsv(summary_tsv_path, [summary_row], SUMMARY_FIELDS)
    _write_tsv(watch_tsv_path, watch_rows, WATCH_FIELDS)
    _write_tsv(all_nodes_tsv_path, node_rows, NODE_FIELDS)
    _write_tsv(history_tsv_path, history_rows, HISTORY_FIELDS)
    _write_tsv(history_totals_tsv_path, history_totals_rows, HISTORY_TOTAL_FIELDS)
    _write_tsv(timeline_tsv_path, timeline_rows, TIMELINE_FIELDS)
    _write_tsv(fire_stage_tsv_path, fire_stage_rows, FIRE_STAGE_FIELDS)
    _write_run_html(
        run_dir,
        manifest,
        summary_row,
        watch_rows,
        evidence,
        events_path,
        history_rows=history_rows,
        history_totals_rows=history_totals_rows,
        timeline_rows=timeline_rows,
        fire_stage_rows=fire_stage_rows,
        figure_links=figure_links,
    )

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
        "- Visual dashboard: `paper_summary.html`",
        "- Events JSONL: `{}`".format(str(Path(events_path).name)),
        "- Summary TSV: `{}`".format(summary_tsv_path.name),
        "- Watch TSV: `{}`".format(watch_tsv_path.name),
        "- All-node TSV: `{}`".format(all_nodes_tsv_path.name),
        "- Pull-history TSV: `{}`".format(history_tsv_path.name),
        "- Pull-totals TSV: `{}`".format(history_totals_tsv_path.name),
        "- Timeline TSV: `{}`".format(timeline_tsv_path.name),
        "- Fire-stage TSV: `{}`".format(fire_stage_tsv_path.name),
        "- Figure exports: `figure_exports/README.md`",
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
        detection_values = [_maybe_float(item.get("detection_speed_sec")) for item in rows]
        detection_values = [float(value) for value in detection_values if value is not None]
        false_positive_values = [int(_to_int(item.get("false_positive_nodes", 0), 0)) for item in rows]
        false_unavailable_values = [int(_to_int(item.get("false_unavailable_refs", 0), 0)) for item in rows]
        settle_accuracy_values = [_maybe_float(item.get("settle_accuracy_pct")) for item in rows]
        settle_accuracy_values = [float(value) for value in settle_accuracy_values if value is not None]
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
                "avg_detection_speed_sec": round(statistics.mean(detection_values), 3) if detection_values else "",
                "avg_false_positive_nodes": round(statistics.mean(false_positive_values), 3) if false_positive_values else 0.0,
                "avg_false_unavailable_refs": round(statistics.mean(false_unavailable_values), 3) if false_unavailable_values else 0.0,
                "avg_settle_accuracy_pct": round(statistics.mean(settle_accuracy_values), 1) if settle_accuracy_values else "",
            }
        )
    return out


def _write_suite_reports(report_dir, spec, summary_rows, watch_rows):
    all_runs_tsv = report_dir / "all_runs.tsv"
    all_watch_tsv = report_dir / "all_watch_nodes.tsv"
    summary_by_nodes_tsv = report_dir / "summary_by_nodes.tsv"
    metric_averages_tsv = report_dir / "metric_averages.tsv"
    comparison_tsv = report_dir / "protocol_comparison.tsv"
    summary_md = report_dir / "README.md"

    _write_tsv(all_runs_tsv, summary_rows, SUMMARY_FIELDS)
    _write_tsv(all_watch_tsv, watch_rows, WATCH_FIELDS)

    summary_by_nodes_rows = _suite_summary_rows(summary_rows)
    comparison_rows = _build_protocol_comparison_rows()
    figure_links = _write_suite_figure_exports(report_dir, summary_rows)
    _write_tsv(summary_by_nodes_tsv, summary_by_nodes_rows, SUMMARY_BY_NODES_FIELDS)
    _write_tsv(metric_averages_tsv, _metric_summary_rows(summary_rows, SUMMARY_CHART_FIELDS), ["metric", "samples", "avg", "min", "max", "latest"])
    _write_tsv(comparison_tsv, comparison_rows, COMPARISON_FIELDS)
    _write_suite_html(report_dir, spec, summary_rows, watch_rows, summary_by_nodes_rows, figure_links=figure_links)

    lines = [
        "# {}".format(spec.get("phase_name", "Paper Evaluation Suite")),
        "",
        "- Suite ID: `{}`".format(spec.get("suite_id", "")),
        "- Protocol: `{}`".format(spec.get("protocol", "")),
        "- Challenge: `{}`".format(spec.get("challenge", "")),
        "- Runs completed: `{}`".format(len(summary_rows)),
        "- Visual dashboard: `index.html`",
        "- Aggregate run table: `all_runs.tsv`",
        "- Watch-node table: `all_watch_nodes.tsv`",
        "- Grouped summary: `summary_by_nodes.tsv`",
        "- Metric averages: `metric_averages.tsv`",
        "- Protocol comparison: `protocol_comparison.tsv`",
        "- Figure exports: `figure_exports/README.md`",
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


def _run_case(spec_for_run, case):
    base_port = _to_int(spec_for_run.get("base_port", 9000), 9000)
    number_of_nodes = int(case["nodes"])
    run_index = int(case["run_index"])
    seed = int(case["seed"])

    _stop_nodes()
    try:
        run_dir = _start_nodes(number_of_nodes)

        if not _wait_until_ready(base_port, number_of_nodes):
            raise RuntimeError("timed out waiting for {} nodes to become reachable".format(number_of_nodes))

        events_path = run_dir / "paper_events.jsonl"
        history_path = run_dir / "paper_pull_history.jsonl"
        history_totals_path = run_dir / "paper_pull_totals.jsonl"
        active_duration_sec, _ = _run_active_window(
            spec_for_run,
            base_port,
            number_of_nodes,
            run_index,
            seed,
            events_path,
            history_path=history_path,
            history_totals_path=history_totals_path,
        )
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
        _write_run_reports(
            run_dir,
            manifest,
            summary_row,
            watch_rows_case,
            evidence,
            events_path,
            history_path=history_path,
            history_totals_path=history_totals_path,
        )
        return {
            "run_dir": run_dir,
            "manifest": manifest,
            "summary_row": summary_row,
            "watch_rows": watch_rows_case,
            "evidence": evidence,
        }
    finally:
        _stop_nodes()


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

    summary_rows = []
    watch_rows = []

    for case in cases:
        result = _run_case(spec_for_run, case)
        summary_rows.append(result["summary_row"])
        watch_rows.extend(result["watch_rows"])
        _write_suite_reports(report_dir, spec_for_run, summary_rows, watch_rows)

    _write_suite_reports(report_dir, spec_for_run, summary_rows, watch_rows)
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
