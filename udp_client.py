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
from killing_thread import KillingThread
from messages import VehicleDataMessage
import socket
import json


class UDPClient:
    def __init__(self, addresses, port=10000):
        """ Constructor
        :param client_id: client id to be used for MQTT broker
        :param broker: IP of MQTT broker
        :param port: port of MQTT broker
        """
        self.port = port
        self.client = None
        self.addresses = addresses
        self.init_udp()
    
    def init_udp(self):
        #server socket
        self.udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_server.bind(('0.0.0.0', self.port))
        self.udp_thread = KillingThread(target=self.udp_worker)
        self.udp_thread.start()
        
        #client sockets #TODO: do we need multiple? probably not since they are statless
        self.udp_sockets = {}
        for a in self.addresses:
            tx_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_sockets[a] = tx_socket

    def udp_worker(self):
        debug("Started UDP Server")
        while True:
            blob, addr = self.udp_server.recvfrom(2014)
            data = json.loads(blob)
            message = VehicleDataMessage()
            if message.from_json(blob):
                self.receive(data['content']['sender'], message)

    def udp_broadcast(self, data):
        for addr in self.udp_sockets.keys():
            self.udp_unicast(data, addr)
    
    def udp_unicast(self, data, addr):
        payload = data.encode('utf-8')
        self.udp_sockets[addr].sendto(payload, (addr, self.port))
    
    def receive(self, source, packet):
        """ Callback invoked by Colosseum when a packet for this vehicle has been received. This method should be
        overridden by inheriting applications
        :param source: sender node id
        :param packet: received data packet
        """
        pass

