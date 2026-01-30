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
# This file provides a set of commonly used functions (the EGESS API),
# which are likely to be used by several different modules of EGESS.
# -------------------------------------------------------------------------

import json # For encoding/decoding JSON objects
import time # For obtaining the timestamps
import requests # For sending POST requests


def log_new_node_state(this_port, apriori_node_state, aposteriori_node_state):
    """
    Add to the log a record of a node state transition in a uniform format.

    Args:
        this_port (int): The port this node listens.
        apriori_node_state (dict[str, Any]): The state of the node (JSON) before the transition.
        aposteriori_node_state (dict[str, Any]): The state of the node (JSON) after the transition.
    """
    print("NODE STATE CHANGED (NODE {}):\nAPRIORI: {}\nAPOSTERIORI: {}\n"
        .format(
                this_port,
                json.dumps(apriori_node_state),
                json.dumps(aposteriori_node_state)
            )
        )


def log_current_node_state(this_port, node_state):
    """
    Add to the log a record of the current state of the node in a uniform format.

    Args:
        this_port (int): The port this node listens.
        apriori_node_state (dict[str, Any]): The state of the node (JSON) before the transition.
        aposteriori_node_state (dict[str, Any]): The state of the node (JSON) after the transition.
    """
    print("NODE STATE CHANGED (NODE {}):\nSTATE: {}\n"
        .format(
                this_port,
                json.dumps(node_state)
            )
        )


def write_data_point(this_port, logtype, message):
    """
    Write a data point to data.csv file.

    Args:
        this_port (int): The port this node listens.
        logtype (str): A unique key for specific type of log.
        message (str): This is the data to be logged at the last column.
    """
    data_file = "data.csv" # The data is piled in data.csv. TODO: Make it custom (optionally)
    with open(data_file, "a") as f: # Open the file in append mode
        # Each record has four comma-separated fields:
        # 1) the port that the node is listening, which is essentially the node's ID;
        # 2) the current timestamp (in floating point format);
        # 3) the unique type of the log, which allows to merge different datasets in one file;
        # 4) the message (data point payload) - make sure to avoid commas in it.
        f.write("{},{},{},{}\n".format(this_port, time.time(), logtype, message)) # Write into the file.
        f.close() # Close the file.


def send_msg(config_json, node_state, state_lock, this_port, msg, target_port):
    """_summary_

    Args:
        config_json (dict[str, Any]): JSON object with all-nodes configuration.
        node_state (dict[str, Any]): The state of this current node.
        state_lock (threading.Lock): The lock object for thread-safety of the state.
        this_port (int): The port this node listens.
        msg (dict[str, Any]): the JSON object to be sent.
        target_port (int): the port (i.e., node ID) of the recipient node.
    """
    
    # Apply the propagation delay as per the latency matrix
    i = this_port - config_json["base_port"] # Convert port to row
    j = target_port - config_json["base_port"] # Conver port to column
    time.sleep(node_state["latency_matrix"][i][j]) # Apply latency
    
    try:
        host_url = "http://" + config_json["base_host"] # Form the URL of the host (without port)
        # Send a POST request to the node with the target port
        resp = requests.post("{}:{}/".format(host_url, target_port), json=msg)

        if resp.status_code == 200: # If request is successful
            resp_json = resp.json() # Obtain the JSON object fo the response
            # And log it
            print("send_msg: MESSAGE SENT ({} -> {}): {}; RESPONSE: {}\n".format(this_port, target_port, msg, resp_json))
            # TODO: Consider return value
        else: # The POST request wasn't successful
            # Log the error
            print("ERROR: send_msg: return code is not 200.\n")
        
    except requests.exceptions.ConnectionError: # Connection error
        print("ERROR: send_msg: Connection error.\n") # Log the error

