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
# This file implements the push protocol of the node. The push protocol
# sends the message from the push queue to other nodes.
# -------------------------------------------------------------------------

import copy # For copying lists' data, not references.
import random # For randomly selecting nodes to forward the message to.
import egess_api # For invoking commonly used functions.

def push_protocol(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue, msg):
    """
    This function implements the push protocol for a message taken from the push queue.

    Args:
        config_json (dict[str, Any]): JSON object with all-nodes configuration.
        node_state (dict[str, Any]): The state of this current node.
        state_lock (threading.Lock): The lock object for thread-safety of the state.
        this_port (int): The port this node listens.
        number_of_nodes (int): The total number of nodes in the network (if known).
        push_queue (queue.Queue): The queue for messages to be pushed to other node(s).
        msg (dict[str, Any]): The message (in JSON format) to be pushed.
    """

    # Generate the list of ports of all nodes, which is basically [9000, 9001, 9002, ..., 9000+N].
    all_nodes = list(range(config_json["base_port"], config_json["base_port"] + number_of_nodes, 1))
    # To exclude the current node from all_nodes without altering all_nodes, we have to copy it first.
    other_nodes = copy.copy(all_nodes)
    # And then exclude the current node's port.
    other_nodes.remove(this_port)
    # Now let's take a random.
    node_sample = random.sample(other_nodes, 2)

    # Iterate over the randomly selected sample of nodes.
    for target_port in node_sample:
        # Forward the message to the node from the random sample and log the event.
        egess_api.send_msg(config_json, node_state, state_lock, this_port, msg, target_port)
        print("MESSAGE FORWARDED {} {}\n".format(str(this_port), str(target_port)))

