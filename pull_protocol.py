# EGESS - Experimental Gear for Evaluation of Swarm Systems
# Copyright (C) 2026  Nick Ivanov and ACSUS Lab <ivanov@rowan.edu>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


# -------------------------------------------------------------------------
# This file implements the pull protocol. The pull protocol requests
# updates from other nodes and receives these updates within the response
# to the request (i.e., within the same session).
# -------------------------------------------------------------------------


import egess_api
import random
import copy

def pull_protocol(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue):
    """
    Pull protocol implementation function.

    Args:
        config_json (dict[str, Any]): JSON object with all-nodes configuration.
        node_state (dict[str, Any]): The state of this current node.
        state_lock (threading.Lock): The lock object for thread-safety of the state.
        this_port (int): The port this node listens.
        number_of_nodes (int): The total number of nodes in the network (if known).
        push_queue (queue.Queue): The queue for messages to be pushed to other node(s).
    """    

    # Request for information/update (a.k.a. "polling" message)
    msg = {
        "op": "pull",
        "data": {},
        "metadata": {}
    }

    # Generate the list of all nodes.
    all_nodes = list(range(config_json["base_port"], config_json["base_port"] + number_of_nodes, 1))
    # Copy the list of all nodes to other_nodes.
    other_nodes = copy.copy(all_nodes)
    # Remove the current node's port to come up with the list of all nodes except the current one.
    other_nodes.remove(this_port)
    # Take a random sample of one from the list of other nodes.
    node_sample = random.sample(other_nodes, 1)

    # Send the polling (pull) request to the single randomly selected node from the list of other nodes
    egess_api.send_msg(config_json, node_state, state_lock, this_port, msg, node_sample[0])
    