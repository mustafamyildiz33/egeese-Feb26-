#!/bin/bash

# This script kills all the swarm notes running under the current
# terminal. This script should print nothing. If it prints a process
# running a node, it means that something went wrong with the killing.


# Kill all running nodes.
pkill -f node.py

# List the processes currently running nodes
ps -ef | grep node.py | grep -v grep