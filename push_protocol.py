import time
import copy
import random
import requests
import json

def push_protocol(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue, msg):
    if msg == None:
        return
    else:
        all_nodes = list(range(config_json["base_port"], config_json["base_port"] + number_of_nodes, 1))
        other_nodes = copy.copy(all_nodes)
        other_nodes.remove(this_port)
        # push_protocol.push_protocol(config_json, node_state, this_port, number_of_nodes, other_nodes, msg)

        node_sample = random.sample(other_nodes, 2)
    
        for target_port in node_sample:
            print("MESSAGE FORWARDED {} {}\n".format(str(this_port), str(target_port)))
            send_msg(config_json, node_state, this_port, number_of_nodes, other_nodes, msg, target_port)


def write_data_point(this_port, logtype, message):
    data_file = "data.csv"
    with open(data_file, "a") as f:
        f.write("{},{},{},{}\n".format(this_port, time.time(), logtype, message))
        f.close()


def send_msg(config_json, node_state, this_port, number_of_nodes, other_nodes, msg, target_port):
    try:
        host_url = "http://" + config_json["base_host"]
        resp = requests.post("{}:{}/".format(host_url, target_port), json=msg)

        if resp.status_code == 200:
            write_data_point(this_port, "SEND_MSG", msg["metadata"]["forward_count"])
            resp_json = resp.json()
        else:
            print("ERROR: send_msg: return code is not 200")
        
    except requests.exceptions.ConnectionError:
        print("ERROR: Connection error")