import sys
import json
from flask import Flask, request, jsonify
import threading
import queue
import copy
import numpy as np
import time

import pull_protocol
import push_protocol
import listener_protocol
import daemon_protocol

# import forwarder_protocol
# import listener_protocol
# import pull_protocol

def pull(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue):
    while True:
        pull_protocol.pull_protocol(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue)


def push(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue):
    while True:
        msg = push_queue.get()
        push_protocol.push_protocol(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue, msg)


def listener(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue):
    app = Flask(__name__)

    @app.route("/", methods=['POST'])
    def egess_api():
        if not request.is_json:
            return jsonify({"error": "OOPS: Not JSON!"}), 400
        else:
            msg = request.get_json()
            return listener_protocol.listener_protocol(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue, msg)
    
    app.run(host=config_json["base_host"], port=this_port)


def daemon(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue):
    while True:
        daemon_protocol.daemon_protocol(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue)


def main():
    if len(sys.argv) != 3:
        print("ERROR Two arguments expected.")
        print("USAGE: {} <port> <number_of_nodes>".format(sys.argv[0]))
        exit(1)
    
    config_file = "config.json"
    node_state_init_file = "node_state_init.json"

    this_port = int(sys.argv[1])
    number_of_nodes = int(sys.argv[2])

    with open(config_file) as file:
        config_json = json.load(file)

    with open(node_state_init_file) as file:
        node_state = json.load(file)

    state_lock = threading.Lock()
    
    push_queue = queue.Queue(maxsize=config_json["push_queue_maxsize"])
    push_thread = threading.Thread(target=push, args=(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue))
    push_thread.start()

    listener_thread = threading.Thread(target=listener, args=(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue))
    listener_thread.start()

    pull_thread = threading.Thread(target=pull, args=(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue))
    pull_thread.start()

    daemon_thread = threading.Thread(target=daemon, args=(config_json, node_state, state_lock, this_port, number_of_nodes, push_queue))
    daemon_thread.start()

    daemon_thread.join()
    pull_thread.join()
    listener_thread.join()
    push_thread.join()

if __name__ == "__main__":
    main()