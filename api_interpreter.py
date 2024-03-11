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
from logging import debug, error

import plexe.plexe_imp.plexe_sumo_eclipse
from plexe.plexe_imp.ccparams import CC_PAR_VEHICLE_DATA, PAR_LEADER_SPEED_AND_ACCELERATION, \
    PAR_PRECEDING_SPEED_AND_ACCELERATION, PAR_CC_DESIRED_SPEED, PAR_ACTIVE_CONTROLLER
from plexe.vehicle_data import VehicleData
from traci import FatalTraCIError

from constants import TOPIC_API_RESPONSE
from messages import APICallMessage, VehicleDataMessage, APIResponseMessage


class APIInterpreter:
    """ Class used to interpret API call sent to Colosseumo and translate them into actual TraCI calls
    """
    def __init__(self, traci, plexe):
        self.traci = traci
        self.plexe = plexe

    @staticmethod
    def __plexe_vehicle_data_to_mqtt(sumo_id, data):
        return VehicleDataMessage(sumo_id, data.u, data.acceleration, data.speed, data.time, data.pos_x, data.pos_y)

    @staticmethod
    def __mqtt_to_plexe_vehicle_data(msg):
        return VehicleData(None, msg.controller_acceleration, msg.acceleration, msg.speed, msg.x, msg.y, msg.time)

    def serve_api_call(self, topic, payload):
        _, sumo_id = topic.split("/")
        response_topic = TOPIC_API_RESPONSE.format(sumo_id=sumo_id)
        call_msg = APICallMessage()
        debug(f"Serving API call received on {topic} with content {payload}")
        if call_msg.from_json(payload):
            response = APIResponseMessage(sumo_id, call_msg.api_code, call_msg.transaction_id)
            try:
                if call_msg.api_code == CC_PAR_VEHICLE_DATA:
                    data = self.plexe.get_vehicle_data(sumo_id)
                    result = self.__plexe_vehicle_data_to_mqtt(sumo_id, data)
                    response.set_field("response", result.to_json())
                if call_msg.api_code == PAR_LEADER_SPEED_AND_ACCELERATION:
                    msg = VehicleDataMessage()
                    msg.from_json(call_msg.parameters)
                    data = self.__mqtt_to_plexe_vehicle_data(msg)
                    self.plexe.set_leader_vehicle_data(sumo_id, data)
                    response.set_field("response", "true")
                if call_msg.api_code == PAR_PRECEDING_SPEED_AND_ACCELERATION:
                    msg = VehicleDataMessage()
                    msg.from_json(call_msg.parameters)
                    data = self.__mqtt_to_plexe_vehicle_data(msg)
                    self.plexe.set_front_vehicle_data(sumo_id, data)
                    response.set_field("response", "true")
                if call_msg.api_code == PAR_CC_DESIRED_SPEED:
                    msg = VehicleDataMessage()
                    msg.from_json(call_msg.parameters)
                    self.plexe.set_cc_desired_speed(sumo_id, msg.speed)
                    response.set_field("response", "true")
                if call_msg.api_code == PAR_ACTIVE_CONTROLLER:
                    controller = int(call_msg.parameters)
                    self.plexe.set_active_controller(sumo_id, controller)
                    response.set_field("response", "true")
            except FatalTraCIError as e:
                error(f"TraCI returned exception {e}")
                response = None
        if response is not None:
            debug(f"Returning response {response.to_json()} on topic {topic}")
        return response_topic, response
