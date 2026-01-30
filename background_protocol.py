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
# This file contains the background protocol of the node. The background
# protocol is running by itself and is not directly triggered by messages
# or queues.
# -------------------------------------------------------------------------



import egess_api # To access common EGESS functions

def background_protocol(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue):
     """
     Background protocol function. It is called with a certain frequency/period specified
     in the all-nodes configuration.

     Args:
          config_json (dict[str, Any]): JSON object with all-nodes configuration.
          node_state (dict[str, Any]): The state of this current node.
          state_lock (threading.Lock): The lock object for thread-safety of the state.
          this_port (int): The port this node listens.
          number_of_nodes (int): The total number of nodes in the network (if known).
          push_queue (queue.Queue): The queue for messages to be pushed to other node(s).
     """
     state_lock.acquire() # Prevent state access by other threads
     # Increment the number of background hits (invocations of this function) recorded
     # in the node's state
     node_state["background_hits"] = node_state["background_hits"] + 1
     # Log current node state (the message will appear in run.log)
     egess_api.log_current_node_state(this_port, node_state)
     # Add the state change data point.
     egess_api.write_state_change_data_point(this_port, node_state, "background_hits")
     state_lock.release() # Allow state access by other threads


