import json
import requests
import numpy as np

def main():
    trigger_msg_file = "trigger_msg.json"
    config_file = "config.json"

    with open(config_file) as file:
        config_json = json.load(file)

    with open(trigger_msg_file) as file:
        trigger_msg = json.load(file)

    try:
        resp = requests.post("http://{}:{}/".format(config_json["base_host"], config_json["base_port"]), json=trigger_msg)

        if resp.status_code == 200:
            resp_json = resp.json()
            print("RESPONSE: ", json.dumps(resp_json, indent=4))
    except requests.exceptions.ConnectionError:
        print("ERROR: Connection error")


if __name__ == "__main__":
    main()
