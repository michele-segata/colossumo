#
# Copyright (c) 2024 Michele Segata <segata@ccs-labs.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.
#

from logging import error, debug, DEBUG, basicConfig
import paho.mqtt.client as mqtt


class MQTTClient:
    def __init__(self, client_id, broker, port):
        """ Constructor
        :param client_id: client id to be used for MQTT broker
        :param broker: IP of MQTT broker
        :param port: port of MQTT broker
        """
        self.client_id = client_id
        self.broker = broker
        self.port = port
        self.client = None

    def on_connect(self, client, userdata, flags, rc, properties):
        if rc == 0:
            debug("Connected to MQTT Broker!")
        else:
            error("Failed to connect, return code %d\n", rc)

    def connect_mqtt(self):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, self.client_id)
        self.client = client
        client.username_pw_set("user", "pwd")
        client.on_connect = self.on_connect
        client.connect(self.broker, self.port)
        client.loop_start()

    def disconnect_mqtt(self):
        if self.is_connected():
            self.client.loop_stop()
            self.client.disconnect()

    def publish(self, topic, data):
        result = self.client.publish(topic, data)
        # result: [0, 1]
        status = result[0]
        return status == 0

    def on_message(self, client, userdata, msg):
        # to be overriden by inheriting classes
        pass

    def subscribe(self, topic):
        self.client.subscribe(topic)
        self.client.on_message = self.on_message

    def is_connected(self):
        return self.client.is_connected()
