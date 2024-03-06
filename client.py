import paho.mqtt.client as mqtt
from messages import StartSimulationMessage, MQTTUpdate, StopSimulationMessage
import sys

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "dummy_client")
client.username_pw_set("user", "pwd")
client.connect(sys.argv[1], 1883)

msg = StartSimulationMessage()
client.publish("colosseum/update", msg.to_json())