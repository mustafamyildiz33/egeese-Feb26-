# EGESS - Experimental Gear for Evaluation of Swarm Systems
# Copyright (C) 2026  Nick Ivanov and ACSUS Lab <ivanov@rowan.edu>

import os
import time
import egess_api


def _demo_mode() -> bool:
    return os.environ.get("DEMO_MODE", "0") == "1"


def _reading_for_sensor_state(sensor_state):
    state = str(sensor_state).strip().upper()
    if state == "ALERT":
        return "RED"
    if state == "RECOVERING":
        return "GREEN"
    return "BLUE"


def _apply_sensor_faults(node_state):
    """Apply synthetic sensor faults before the node publishes its local reading.

    Args:
        node_state: Mutable node runtime state.

    Returns:
        A sanitized sensor state string after fault injection is applied.
    """
    faults = node_state.get("faults", {})
    if not isinstance(faults, dict):
        faults = {}
        node_state["faults"] = faults

    lie_sensor = bool(faults.get("lie_sensor", False))
    flap = bool(faults.get("flap", False))
    period_sec = int(faults.get("period_sec", 4))
    if period_sec < 1:
        period_sec = 1

    if flap:
        tick = int(time.time() // period_sec)
        return "ALERT" if (tick % 2) == 0 else "NORMAL"

    if lie_sensor:
        return "ALERT"

    sensor_state = str(node_state.get("sensor_state", "NORMAL")).strip().upper()
    if sensor_state not in ("NORMAL", "ALERT", "RECOVERING"):
        return "NORMAL"
    return sensor_state


def background_protocol(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue):
    state_lock.acquire()
    try:
        node_state["background_hits"] = int(node_state.get("background_hits", 0)) + 1

        sensor_state = _apply_sensor_faults(node_state)
        node_state["sensor_state"] = sensor_state
        node_state["local_reading"] = _reading_for_sensor_state(sensor_state)

        if not _demo_mode():
            egess_api.log_current_node_state(this_port, node_state)
            egess_api.write_state_change_data_point(this_port, node_state, "background_hits")
    finally:
        state_lock.release()
