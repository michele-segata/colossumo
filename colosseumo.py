#!/usr/bin/env python
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

import os
import random
import sys
from argparse import ArgumentParser
from importlib import import_module
from logging import error, debug, DEBUG, basicConfig
from os.path import split, join
from time import sleep
from pyproj.crs.crs import CRS

from libxml2 import parseFile
import paho.mqtt.client as mqtt
from plexe import Plexe
from traci.constants import TRACI_ID_LIST, VAR_POSITION

from bidict import Bidict
from messages import MQTTUpdate, DeleteVehicleMessage, NewVehicleMessage, PositionUpdateMessage, CurrentTimeMessage
from utils import start_sumo

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")
import traci


SUMO_UPDATE_TOPIC = "sumo/update"


class Colosseumo:
    def __init__(self, client_id, broker, port, config, scenario, available_nodes):
        """ Constructor
        :param client_id: client id to be used for MQTT broker
        :param broker: IP of MQTT broker
        :param port: port of MQTT broker
        :param config: sumo config file (.cfg)
        :param scenario: python script implementing the scenario (must subclass scenario.py)
        :param available_nodes: list of nodes available in colosseum. TODO: automatically retrieve this list in future
        """
        self.client_id = client_id
        self.broker = broker
        self.port = port
        self.connected = False
        self.client = None
        self.listeners = []
        self.config = config
        self.scenario = scenario
        self.sumo_vehicles = set()
        # list of available node ids in colosseum
        self.available_nodes = set(available_nodes)
        # map from sumo vehicle id to colosseum node id
        self.vehicle_to_node = Bidict()
        # whether to use geo coordinates or simple x-y coordinates (in absence of geo reference)
        self.use_geo_coord = False
        # CRS code for coordinate projection
        self.crs = None
    def on_connect(self, client, userdata, flags, rc, properties):
        if rc == 0:
            self.connected = True
            debug("Connected to MQTT Broker!")
        else:
            error("Failed to connect, return code %d\n", rc)

    def connect_mqtt(self):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, self.client_id)
        client.username_pw_set("user", "pwd")
        client.on_connect = self.on_connect
        client.connect(self.broker, self.port)
        client.loop_start()
        self.client = client

    def disconnect_mqtt(self):
        if self.connected:
            self.client.loop_stop()
            self.client.disconnect()

    def publish(self, topic, data):
        result = self.client.publish(topic, data)
        # result: [0, 1]
        status = result[0]
        return status == 0

    def on_message(self, client, userdata, msg):
        print(f"Received `{msg.payload.decode()}` from `{msg.topic}` topic")
        for listener in self.listeners:
            listener(msg)

    def subscribe(self, topic):
        self.client.subscribe(topic)
        self.client.on_message = self.on_message

    def add_listener(self, listener):
        self.listeners.append(listener)

    def assign_free_colosseum_node(self, sumo_vehicle):
        if len(self.available_nodes) == 0:
            return -1
        else:
            colosseum_node = self.available_nodes.pop()
            self.vehicle_to_node[sumo_vehicle] = colosseum_node
            return colosseum_node

    def release_colosseum_node(self, sumo_vehicle):
        if sumo_vehicle not in self.vehicle_to_node.keys():
            return -1
        else:
            colosseum_node = self.vehicle_to_node[sumo_vehicle]
            self.available_nodes.add(colosseum_node)
            return colosseum_node

    def get_colosseum_node(self, sumo_vehicle_id):
        if sumo_vehicle_id not in self.vehicle_to_node.keys():
            return -1
        else:
            return self.vehicle_to_node[sumo_vehicle_id]

    def get_sumo_vehicle(self, colosseum_node_id):
        inv_map = self.vehicle_to_node.inverse()
        if colosseum_node_id not in inv_map.keys():
            return ""
        else:
            return inv_map[colosseum_node_id]

    def compute_coordinate_system(self):
        sumo_cfg_doc = parseFile(self.config)
        context = sumo_cfg_doc.xpathNewContext()
        # get sumo net file
        net_file = context.xpathEval("string(//configuration/input/net-file/@value)")
        if net_file == "":
            return False
        config_folder, _ = split(self.config)
        sumo_net_doc = parseFile(join(config_folder, net_file))
        context = sumo_net_doc.xpathNewContext()
        # get coordinate system if present
        coordinate_system = context.xpathEval("string(//net/location/@projParameter)")
        if coordinate_system == "" or coordinate_system == "!":
            return False
        # load coordinate reference system
        crs = CRS.from_string(coordinate_system)
        self.crs = ":".join(crs.to_authority())
        self.use_geo_coord = True
        return True

    def run_simulation(self, max_time):
        self.compute_coordinate_system()
        # used to randomly color the vehicles
        random.seed(1)
        start_sumo(self.config, False), 
        plexe = Plexe()
        traci.addStepListener(plexe)
        step = 0
        current_time = 0
        scenario = self.scenario(traci, plexe)
        traci.vehicle.subscribe("", [TRACI_ID_LIST])
        while current_time <= max_time:
            update_msg = MQTTUpdate()
            traci.simulationStep()
            scenario.step(step)
            debug("Running simulation step number {}".format(step))

            # inform colosseum about current simulation time
            current_time = traci.simulation.getTime()
            update_msg.add(CurrentTimeMessage(current_time))
            debug("Current simulation time: {}".format(current_time))

            # get all updated data
            subscriptions = traci.vehicle.getAllSubscriptionResults()

            # check for new vehicles or deleted ones
            new_vehicles, old_vehicles = self.update_vehicles(subscriptions[''][TRACI_ID_LIST])

            # tell colosseum about all vehicles to be removed, releasing testbed nodes
            for sumo_vehicle in old_vehicles:
                colosseum_node = self.get_colosseum_node(sumo_vehicle)
                if colosseum_node == -1:
                    error("Error: removed vehicle from SUMO (id={}) not currently registered".format(sumo_vehicle))
                else:
                    # don't get updates anymore
                    traci.vehicle.unsubscribe(sumo_vehicle)

                    self.release_colosseum_node(sumo_vehicle)
                    m = DeleteVehicleMessage(sumo_vehicle, colosseum_node)
                    update_msg.add(m)
                    debug("Removing SUMO vehicle {} from simulation and releasing colosseum node {}"
                          .format(sumo_vehicle, colosseum_node))

            # tell colosseum about new vehicles and the mapping between the vehicle and node
            for sumo_vehicle in new_vehicles:
                colosseum_node = self.assign_free_colosseum_node(sumo_vehicle)
                if colosseum_node == -1:
                    error("Error: no available free node in colosseum for SUMO vehicle (id={}) ".format(sumo_vehicle))
                else:
                    m = NewVehicleMessage(sumo_vehicle, colosseum_node)
                    update_msg.add(m)

                    # get info about vehicle at each time step
                    traci.vehicle.subscribe(sumo_vehicle, [VAR_POSITION])

                    # we don't need to fetch initial vehicle position from SUMO
                    # apparently subscribing magically adds vehicle data to the variable "subscriptions"
                    # # tell colosseum about the initial node position
                    # x, y = traci.vehicle.getPosition(sumo_vehicle)
                    # m = PositionUpdateMessage(colosseum_node, x, y)
                    # update_msg.add(m)
                    debug("Adding new SUMO vehicle {} to simulation and assigning it to colosseum node {}"
                          .format(sumo_vehicle, colosseum_node))

            for sumo_vehicle in self.vehicle_to_node.keys():
                if sumo_vehicle not in subscriptions.keys():
                    error("Vehicle {} not in subscription results".format(sumo_vehicle))
                else:
                    colosseum_node = self.get_colosseum_node(sumo_vehicle)
                    if colosseum_node == -1:
                        error("SUMO vehicle {} is not associated to any node in colosseum".format(sumo_vehicle))
                    else:
                        x, y = subscriptions[sumo_vehicle][VAR_POSITION]
                        if self.use_geo_coord:
                            x_geo, y_geo = traci.simulation.convertGeo(x, y)
                            m = PositionUpdateMessage(colosseum_node, x_geo, y_geo, self.crs)
                            debug("SUMO vehicle {} geo coordinates: x={}, y={} ({})"
                                  .format(sumo_vehicle, x_geo, y_geo, self.crs))
                        else:
                            m = PositionUpdateMessage(colosseum_node, x, y)

                        update_msg.add(m)
                        debug("Updating SUMO vehicle {} (colosseum node {}) position (x={}, y={})"
                              .format(sumo_vehicle, colosseum_node, x, y, self.crs))

            self.publish(SUMO_UPDATE_TOPIC, update_msg.to_json())
            debug("Publishing update to topic {}:\n{}".format(SUMO_UPDATE_TOPIC, update_msg.to_json()))

            step += 1

        update_msg = MQTTUpdate()
        for sumo_vehicle in self.vehicle_to_node.keys():
            colosseum_node = self.get_colosseum_node(sumo_vehicle)
            if colosseum_node == -1:
                error("Error: vehicle from SUMO (id={}) not currently registered".format(sumo_vehicle))
            else:
                self.release_colosseum_node(sumo_vehicle)
                m = DeleteVehicleMessage(sumo_vehicle, colosseum_node)
                update_msg.add(m)
                debug("Removing SUMO vehicle {} from simulation and releasing colosseum node {}"
                      .format(sumo_vehicle, colosseum_node))
        self.publish(SUMO_UPDATE_TOPIC, update_msg.to_json())
        debug("Publishing update to topic {}:\n{}".format(SUMO_UPDATE_TOPIC, update_msg.to_json()))

        debug("Closing simulation")
        traci.close()

    def update_vehicles(self, sumo_vehicles):
        new_vehicles = set(sumo_vehicles).difference(self.sumo_vehicles)
        old_vehicles = self.sumo_vehicles.difference(set(sumo_vehicles))
        self.sumo_vehicles = set(sumo_vehicles)
        return new_vehicles, old_vehicles

    def is_connected(self):
        return self.connected


def main():
    # set debug level
    basicConfig(level=DEBUG)
    parser = ArgumentParser(description="ColosSeUMO: coupling framework between Colosseum and SUMO")
    parser.add_argument("--broker", help="IP address of the broker", default="127.0.0.1")
    parser.add_argument("--port", help="Port of the broker", default=12345, type=int)
    parser.add_argument("--config", help="SUMO config file")
    parser.add_argument("--scenario", help="Python scenario to instantiate", default="scenario.Scenario")
    parser.add_argument("--nodes", help="Number of available nodes in colosseum", default=32, type=int)
    parser.add_argument("--time", help="Maximum simulation time in seconds", default=60, type=int)
    args = parser.parse_args()
    module, class_name = args.scenario.rsplit(".", 1)
    m = import_module(module)
    scenario = getattr(m, class_name)
    colosseumo = Colosseumo("sumo", args.broker, args.port, args.config, scenario, list(range(args.nodes)))
    colosseumo.connect_mqtt()
    attempt = 1
    while not colosseumo.is_connected() and attempt <= 10:
        debug("Waiting to be connected to MQTT broker. Attempt {}".format(attempt))
        attempt += 1
        sleep(1)

    if not colosseumo.is_connected():
        error("Cannot connect to MQTT broker. Simulation will not start")
    else:
        debug("Connected to MQTT broker. Starting simulation")
        colosseumo.run_simulation(args.time)


if __name__ == "__main__":
    main()
