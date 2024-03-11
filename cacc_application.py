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
from logging import debug, warning
from time import sleep
import time

from plexe.plexe_imp.ccparams import PAR_LEADER_SPEED_AND_ACCELERATION, PAR_PRECEDING_SPEED_AND_ACCELERATION, \
    CC_PAR_VEHICLE_DATA, PAR_CC_DESIRED_SPEED

from application import Application
from messages import VehicleDataMessage


class CACCApplication(Application):
    def __init__(self, client_id, broker, port, sumo_id, colosseum_id, parameters, test_mode, addresses):
        """ Initializer method
        :param client_id: client id to be used for MQTT broker
        :param broker: ip address of the MQTT broker
        :param port: port of the MQTT broker
        :param sumo_id: id of this vehicle in sumo
        :param colosseum_id: id of corresponding colosseum node. TODO: check whether needed or not
        :param parameters: dictionary with parameters. This includes the platoon formation and the beacon interval.
        See parse_parameters() for more info
        :param test_mode: boolean indicating whether using the real communication stack or not
        """
        self.formation = None
        self.position = None
        self.is_leader = None
        self.is_last = None
        self.leader = None
        self.preceding = None
        self.following = None
        self.beacon_interval = None
        self.min_speed = None
        self.max_speed = None
        self.beacon_id = 0
        super().__init__(client_id, broker, port, sumo_id, colosseum_id, parameters, test_mode, addresses)

    def parse_parameters(self):
        """ Parameters expected in self.parameters:
        platoon_formation: formation of the platoon this vehicle is currently in (list of sumo ids)
        beacon_interval: interval between beacons being set (in seconds)
        test_mode: whether the application is running on the real colosseum communication stack or not
        """
        self.formation = self.parameters["platoon_formation"]
        self.position = self.formation.index(self.sumo_id)
        self.is_leader = self.position == 0
        self.is_last = self.position == len(self.formation) - 1
        if not self.is_leader:
            self.leader = self.formation[0]
            self.preceding = self.formation[self.position-1]
            if not self.is_last:
                self.following = self.formation[self.position+1]
            else:
                self.following = None
        else:
            self.leader = None
            self.preceding = None
            self.following = self.formation[self.position+1]
        self.beacon_interval = float(self.parameters["beacon_interval"])
        self.min_speed = float(self.parameters["min_speed"])
        self.max_speed = float(self.parameters["max_speed"])

    def on_start_application(self):
        self.start_thread(self.beaconing_thread)
        if self.is_leader:
            self.start_thread(self.change_speed_thread)

    def receive(self, source, packet):
        # leader uses no other vehicle data
        self.log_packet(source, packet)
        if self.is_leader:
            return
        if source == self.leader or source == self.preceding:
            warning(f"{self.sumo_id} received packet from {source}: {packet.to_json()}")
            if source == self.leader:
                self.call_plexe_api(PAR_LEADER_SPEED_AND_ACCELERATION, packet.to_json())
            if source == self.preceding:
                self.call_plexe_api(PAR_PRECEDING_SPEED_AND_ACCELERATION, packet.to_json())

    def send_beacon(self):
        data = self.call_plexe_api(CC_PAR_VEHICLE_DATA, self.sumo_id)
        if data is None:
            return
        #log current location even if I am the last
        msg = VehicleDataMessage(seqn=self.beacon_id)
        msg.from_json(data)
        self.log_position({'x':msg.content['x'], 'y': msg.content['y']})
        
        #TODO: fix questa porcata
        if self.is_last:
            return
    
        msg.sender = self.sumo_id
        msg.content["sender"] = self.sumo_id
        msg.content["ts"] = time.time()
        msg.content["seqn"] = self.beacon_id
        
        if self.is_leader:
            for i in range(1, len(self.formation)):
                msg.content['recipient'] = self.formation[i]
                data = msg.to_json()
                self.transmit(self.formation[i], data)
        else:
            msg.content['recipient'] = self.following
            data = msg.to_json()
            self.transmit(self.following, data)
        self.beacon_id+=1

    def change_speed_thread(self):
        msg = VehicleDataMessage()
        while self.run:
            # accelerate first
            msg.set_field("speed", 25)
            self.call_plexe_api(PAR_CC_DESIRED_SPEED, msg.to_json())
            sleep(10)
            # then brake
            msg.set_field("speed", 15)
            self.call_plexe_api(PAR_CC_DESIRED_SPEED, msg.to_json())
            sleep(10)
            # then repeat

    def beaconing_thread(self):
        while self.run:
            self.send_beacon()
            sleep(self.beacon_interval)
