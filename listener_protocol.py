import time
import json
import copy

def log_new_node_state(this_port, apriori_node_state, aposteriori_node_state):
    print("NODE STATE CHANGED (NODE {}):\nAPRIORI: {}\nAPOSTERIORI: {}\n".format(this_port, json.dumps(apriori_node_state), json.dumps(aposteriori_node_state)))

def listener_protocol(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue, msg):
    # IMPORTANT: KEEP THIS SAFEGUARD INTACT! Otherwise, the network might be inundated with runaway transactions
    if msg["metadata"]["forward_count"] < config_json["max_forwards"]:
        msg["metadata"]["forward_count"] = msg["metadata"]["forward_count"] + 1
        
        state_lock.acquire()
        apriori_node_state = copy.copy(node_state)
        node_state["accepted_messages"] = node_state["accepted_messages"] + 1
        log_new_node_state(this_port, apriori_node_state, node_state)

        apriori_node_state = copy.copy(node_state)
        if msg["metadata"]["relay"] not in node_state["known_nodes"]:
            node_state["known_nodes"].append(msg["metadata"]["relay"])
            log_new_node_state(this_port, apriori_node_state, node_state)

        state_lock.release()

        msg["metadata"]["relay"] = this_port

        push_queue.put(msg)

        return {
            "enqueued": True
        }
    else:
        return {
            "enqueued": False
        }