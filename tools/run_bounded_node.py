#!/usr/bin/env python3
"""Run one node while writing bounded stdout/stderr logs.

This wrapper exists so start_nodes.sh can record one PID per node even when
logs are size-capped. When the wrapper receives SIGTERM, it terminates the
child node process too.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path


child: subprocess.Popen[bytes] | None = None
stopping = False


def _to_int(value: str, fallback: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(fallback)


def _trim(path: Path, max_bytes: int) -> None:
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return
    if size <= max_bytes:
        return
    with path.open("rb") as handle:
        handle.seek(max(0, size - max_bytes))
        payload = handle.read()
    path.write_bytes(payload)


def _stop_child(*_args) -> None:
    global stopping
    stopping = True
    proc = child
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
    except Exception:
        pass


def main() -> int:
    global child
    if len(sys.argv) != 7:
        print(
            "usage: run_bounded_node.py <python_bin> <node_py> <port> <nodes> <log_path> <max_bytes>",
            file=sys.stderr,
        )
        return 2

    python_bin, node_py, port, nodes, log_path_raw, max_bytes_raw = sys.argv[1:]
    log_path = Path(log_path_raw)
    max_bytes = max(4096, _to_int(max_bytes_raw, 65536))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("", encoding="utf-8")

    signal.signal(signal.SIGTERM, _stop_child)
    signal.signal(signal.SIGINT, _stop_child)

    child = subprocess.Popen(
        [python_bin, "-u", node_py, str(port), str(nodes)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )

    pending = 0
    with log_path.open("ab", buffering=0) as handle:
        assert child.stdout is not None
        while True:
            chunk = child.stdout.readline()
            if not chunk:
                break
            handle.write(chunk)
            pending += len(chunk)
            if pending >= max_bytes:
                pending = 0
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
                _trim(log_path, max_bytes)

    _trim(log_path, max_bytes)
    if stopping and child.poll() is None:
        _stop_child()
    try:
        return int(child.wait(timeout=2))
    except subprocess.TimeoutExpired:
        try:
            child.kill()
        except Exception:
            pass
        return 143


if __name__ == "__main__":
    raise SystemExit(main())
