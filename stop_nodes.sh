#!/bin/bash
set -e

cd "$(dirname "$0")"

BASE_PORT=""
RUN_DIR=""
KILL_ALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-port)
      BASE_PORT="$2"
      shift 2
      ;;
    --run-dir)
      RUN_DIR="$2"
      shift 2
      ;;
    --all)
      KILL_ALL=1
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      echo "Usage: ./stop_nodes.sh [--base-port PORT] [--run-dir runs/<timestamp>] [--all]"
      exit 1
      ;;
  esac
done

if [[ -z "$RUN_DIR" ]]; then
  if [[ -n "$BASE_PORT" ]]; then
    RUN_DIR="$(ls -1dt runs/*_p"${BASE_PORT}" 2>/dev/null | head -n 1 || true)"
  else
    RUN_DIR="$(ls -1dt runs/* 2>/dev/null | head -n 1 || true)"
  fi
fi

kill_pids_file() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    kill "$pid" 2>/dev/null || true
  done < "$file"
}

if [[ -n "$BASE_PORT" ]]; then
  MAX_NODES=0
  shopt -s nullglob
  for pids_file in runs/*_p"${BASE_PORT}"/pids.txt; do
    count="$(wc -l < "$pids_file" | tr -d ' ')"
    if [[ "$count" =~ ^[0-9]+$ && "$count" -gt "$MAX_NODES" ]]; then
      MAX_NODES="$count"
    fi
    kill_pids_file "$pids_file"
  done
  shopt -u nullglob

  if [[ "$MAX_NODES" -gt 0 ]]; then
    END_PORT=$((BASE_PORT + MAX_NODES - 1))
    for port in $(seq "$BASE_PORT" "$END_PORT"); do
      pkill -f "node.py ${port} " 2>/dev/null || true
    done
  fi
elif [[ -n "$RUN_DIR" && -f "$RUN_DIR/pids.txt" ]]; then
  kill_pids_file "$RUN_DIR/pids.txt"
fi

if [[ "$KILL_ALL" -eq 1 ]]; then
  pkill -f "node.py [0-9][0-9]* [0-9][0-9]*" 2>/dev/null || true
fi
