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
from json import loads
from logging import error, debug, DEBUG, basicConfig
from os.path import split, join
from threading import Thread
from time import sleep
from pyproj.crs.crs import CRS

from libxml2 import parseFile
import paho.mqtt.client as mqtt
from plexe import Plexe
from traci import TraCIException, FatalTraCIError
from traci.constants import TRACI_ID_LIST, VAR_POSITION

from api_interpreter import APIInterpreter
from application import Application
from bidict import Bidict
from constants import COLOSSEUM_UPDATE_TOPIC, SUMO_UPDATE_TOPIC, TOPIC_API_CALL, TOPIC_API_PREFIX
from killing_thread import KillingThread
from messages import MQTTUpdate, DeleteVehicleMessage, NewVehicleMessage, PositionUpdateMessage, CurrentTimeMessage, \
    StartSimulationMessage, StopSimulationMessage
from mqtt_client import MQTTClient
from utils import start_sumo

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")
import traci


class Colosseumo(MQTTClient):
    def __init__(self, client_id, broker, port, config, scenario, application, parameters, available_nodes, gui, test):
        """ Constructor
        :param client_id: client id to be used for MQTT broker
        :param broker: IP of MQTT broker
        :param port: port of MQTT broker
        :param config: sumo config file (.cfg)
        :param scenario: python script implementing the scenario (must subclass scenario.py)
        :param application: python application that each node should instantiate on top of the radio interface. If
        Colosseum is used, then this parameter should be a string indicating the class to instantiate, otherwise
        an instantiable python class inheriting from Application
        :param parameters: json string with simulation parameters
        :param available_nodes: list of nodes available in colosseum. TODO: automatically retrieve this list in future
        :param gui: use SUMO in GUI mode or not
        :param test: Boolean: in test mode, Colosseum is not used and communication is handled by Colosseumo
        """
        super().__init__(client_id, broker, port)
        self.listeners = []
        self.config = config
        self.scenario = scenario
        self.application = application
        self.sim_parameters = parameters
        self.applications = dict()
        self.applications_to_start = []
        self.sumo_vehicles = set()
        # list of available node ids in colosseum
        self.available_nodes = set(available_nodes)
        # map from sumo vehicle id to colosseum node id
        self.vehicle_to_node = Bidict()
        # use SUMO GUI/CLI mode
        self.gui = gui
        # enable/disable test mode (w/o or w/ colosseun)
        self.test_mode = test
        # SUMO timestep
        self.timestep = None
        # whether to use geo coordinates or simple x-y coordinates (in absence of geo reference)
        self.use_geo_coord = False
        # CRS code for coordinate projection
        self.crs = None
        # waiting colosseum signal to start the simulation
        self.waiting_for_colosseum = False
        # signal from colosseum to stop simulation
        self.stop_simulation = False
        # API interpreter utility
        self.api_interpreter = None
    
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
        payload = msg.payload.decode()
        debug("Received {} from {} topic".format(payload, msg.topic))
        for listener in self.listeners:
            listener(msg)
        if msg.topic == COLOSSEUM_UPDATE_TOPIC:
            m = loads(payload)
            if "type" in m.keys():
                if m["type"] == StartSimulationMessage.TYPE:
                    self.waiting_for_colosseum = False
                if m["type"] == StopSimulationMessage.TYPE:
                    self.stop_simulation = True
        if msg.topic.startswith(TOPIC_API_PREFIX):
            response_topic, result = self.api_interpreter.serve_api_call(msg.topic, payload)
            if result is not None:
                self.publish(response_topic, result.to_json())

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

    def load_sumo_config(self):
        """ Retrieve sumo configuration data such as the coordinate reference system and the simulation timestep
        """
        sumo_cfg_doc = parseFile(self.config)
        context = sumo_cfg_doc.xpathNewContext()
        # get simulation timestep
        self.timestep = float(context.xpathEval("string(//configuration/time/step-length/@value)"))
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
        self.use_geo_coord = False
        return True

    def process_new_vehicles(self, new_vehicles, update_msg):
        # tell colosseum about new vehicles and the mapping between the vehicle and node
        for sumo_vehicle in new_vehicles:
            # TODO: currently we assume that all vehicles are created at the beginning of the simulation
            # this logic needs to be changed in the future if we want to allow vehicles to be created afterwards
            # Basically if a new vehicle is created, we are at the beginning, so we tell colosseum about them
            # and then wait for colosseum for the start signal
            if not self.test_mode:
                self.waiting_for_colosseum = True
            colosseum_node = self.assign_free_colosseum_node(sumo_vehicle)
            if colosseum_node == -1:
                error("Error: no available free node in colosseum for SUMO vehicle (id={}) ".format(sumo_vehicle))
            else:
                application = None if self.test_mode else self.application
                parameters = None if self.test_mode else self.sim_parameters
                m = NewVehicleMessage(sumo_vehicle, colosseum_node, application, parameters)
                update_msg.add(m)

                # get info about vehicle at each time step
                traci.vehicle.subscribe(sumo_vehicle, [VAR_POSITION])

                # subscribe to MQTT topic to receive API calls from the vehicle
                self.subscribe(TOPIC_API_CALL.format(sumo_id=sumo_vehicle))

                if self.test_mode:
                    app = self.application(sumo_vehicle, self.broker, self.port, sumo_vehicle, colosseum_node,
                                           self.sim_parameters, self.test_mode, None)
                    self.applications[sumo_vehicle] = app
                    # don't start the application, we might need to wait for colosseum to give us green light
                    self.applications_to_start.append(app)
                debug("Adding new SUMO vehicle {} to simulation and assigning it to colosseum node {}"
                      .format(sumo_vehicle, colosseum_node))

    def process_old_vehicles(self, old_vehicles, update_msg):
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
                if self.test_mode:
                    # if we are in test mode, colosseumo instantiated application classes itself
                    # it also needs to kill them
                    app = self.applications[sumo_vehicle]
                    app.stop_application()
                    del self.applications[sumo_vehicle]
                debug("Removing SUMO vehicle {} from simulation and releasing colosseum node {}"
                      .format(sumo_vehicle, colosseum_node))

    def process_subscriptions(self, subscriptions, update_msg):
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

    def run_simulation(self, max_time):
        self.load_sumo_config()
        # used to randomly color the vehicles
        random.seed(1)
        start_sumo(self.config, False, self.gui)
        plexe = Plexe()
        traci.addStepListener(plexe)
        self.api_interpreter = APIInterpreter(traci, plexe)
        step = 0
        current_time = 0
        scenario = self.scenario(traci, plexe, self.gui, self.sim_parameters)
        traci.vehicle.subscribe("", [TRACI_ID_LIST])
        while current_time <= max_time and not self.stop_simulation:

            while self.waiting_for_colosseum:
                debug("List of vehicles sent to Colosseum. Waiting signal to start simulation...")
                sleep(1)

            for app in self.applications_to_start:
                debug(f"Starting application for vehicle {app.sumo_id}")
                app.start_application()
            self.applications_to_start = []

            update_msg = MQTTUpdate()
            try:
                traci.simulationStep()
            except FatalTraCIError:
                debug("Caught TraCI exception. Closing simulation")
                self.stop_simulation = True
                continue

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

            self.process_old_vehicles(old_vehicles, update_msg)
            self.process_new_vehicles(new_vehicles, update_msg)
            self.process_subscriptions(subscriptions, update_msg)

            self.publish(SUMO_UPDATE_TOPIC, update_msg.to_json())
            debug("Publishing update to topic {}:\n{}".format(SUMO_UPDATE_TOPIC, update_msg.to_json()))

            step += 1
            if not self.gui:
                # TODO: here we assume that sumo processing time is 0. needs to be updated in the future
                sleep(self.timestep)

        # exited from main simulation loop because it is terminated. cleanup stuff
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

        if self.test_mode:
            # if we are in test mode, colosseumo instantiated application classes itself
            # it also needs to kill them
            for sumo_vehicle in self.applications.keys():
                app = self.applications[sumo_vehicle]
                app.stop_application()
                del app

        debug("Closing simulation")
        try:
            traci.close()
        except FatalTraCIError:
            # if we come here because sumo has been closed, we cannot close it again
            pass

    def update_vehicles(self, sumo_vehicles):
        new_vehicles = set(sumo_vehicles).difference(self.sumo_vehicles)
        old_vehicles = self.sumo_vehicles.difference(set(sumo_vehicles))
        self.sumo_vehicles = set(sumo_vehicles)
        return new_vehicles, old_vehicles


def main():
    # set debug level
    basicConfig(level=DEBUG)
    parser = ArgumentParser(description="ColosSeUMO: coupling framework between Colosseum and SUMO")
    parser.add_argument("--broker", help="IP address of the broker", default="127.0.0.1")
    parser.add_argument("--port", help="Port of the broker", default=12345, type=int)
    parser.add_argument("--config", help="SUMO config file")
    parser.add_argument("--scenario", help="Python scenario to instantiate", default="scenario.Scenario")
    parser.add_argument("--application", help="Python application each node should run", default="application.Application")
    parser.add_argument("--params", help="File JSON with simulation parameters passed to scenario and application", default="")
    parser.add_argument("--nodes", help="Number of available nodes in colosseum", default=32, type=int)
    parser.add_argument("--time", help="Maximum simulation time in seconds", default=60, type=int)
    parser.add_argument("--gui", help="Use SUMO in GUI mode", action="store_true", default=False)
    parser.add_argument("--test", help="Run without Colosseum", action="store_true", default=False)
    args = parser.parse_args()
    module, class_name = args.scenario.rsplit(".", 1)
    m = import_module(module)
    scenario = getattr(m, class_name)
    broker = args.broker
    port = args.port
    config = args.config
    gui = args.gui
    test = args.test
    if test:
        # if we run in test mode without colosseum, classes are instantiated directly by Colosseumo
        module, class_name = args.application.rsplit(".", 1)
        m = import_module(module)
        application = getattr(m, class_name)
    else:
        # otherwise we will pass the class name to Colosseumo
        application = args.application
    if args.params == "":
        parameters = "{}"
    else:
        with open(args.params) as params_file:
            parameters = params_file.read()
    colosseumo = Colosseumo("sumo", broker, port, config, scenario, application, parameters,
                            list(range(args.nodes)), gui, test)
    colosseumo.connect_mqtt()
    colosseumo.subscribe(COLOSSEUM_UPDATE_TOPIC)
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
