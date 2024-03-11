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
from abc import abstractmethod
from json import loads
from logging import error, debug, warning
from os import _exit
from threading import Lock, Semaphore
import time
import socket
import json

from constants import TOPIC_API_CALL, TOPIC_API_RESPONSE, TOPIC_DIRECT_COMM
from killing_thread import KillingThread
from messages import APICallMessage, APIResponseMessage, VehicleDataMessage
from mqtt_client import MQTTClient

class Application(MQTTClient):
    """ Base class to be used by all applications
    """
    def __init__(self, client_id, broker, port, sumo_id, colosseum_id, parameters, test_mode, addresses):
        """ Initializer method. This method calls the parse_parameters() method of the subclass, which should parse
        what is needed out of simulation parameters. For this reasons, class variables of the subclass must be
        initialized BEFORE calling the super().__init__() method of Application, otherwise the initialization will
        overwrite the parameters just set by the parse_parameters() method
        :param client_id: client id to be used for MQTT broker
        :param broker: ip address of the MQTT broker
        :param port: port of the MQTT broker
        :param sumo_id: id of this vehicle in sumo
        :param colosseum_id: id of corresponding colosseum node. TODO: check whether needed or not
        :param parameters: json string with application parameters
        :param test_mode: boolean indicating whether using the real communication stack or not
        """
        super().__init__(client_id, broker, port)
        self.sumo_id = sumo_id
        self.colosseum_id = colosseum_id
        self.parameters = loads(parameters)
        self.test_mode = test_mode
        self.start_time = -1
        # MQTT topics used to send/receive data to/from SUMO
        self.topic_api_call = TOPIC_API_CALL.format(sumo_id=sumo_id)
        self.topic_api_response = TOPIC_API_RESPONSE.format(sumo_id=sumo_id)
        # variables used to have a synchronous API callback
        # used to understand whether the answer is for the request we made
        self.transaction_id = 0
        # value returned by the api calls
        self.api_call_return_value = {}
        # semaphores used to block each API call to wait for the return value
        self.api_semaphores = {}
        # mutex used to manage the transaction id
        self.mutex_transaction = Lock()
        # set of running threads
        self.threads = []
        self.run = True
        self.parse_parameters()
        self.connect_mqtt()
        #setup udp comms
        self.addresses = addresses
        self.udp_port = 10000 #TODO: should we make this a param?
        self.init_udp()
        #init logfile
        self.mutex_logfile = Lock()
        self.logfile = open(f"logs/{self.sumo_id}.log", "w")
    
    def init_udp(self):
        #server socket
        self.udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_server.bind(('0.0.0.0', self.udp_port))
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
            if message.from_json(blob) and data["content"]["recipient"] == self.sumo_id:
                #process data only if I am the recipient of the packet
                self.receive(data['content']['sender'], message)

    def udp_broadcast(self, data):
        for addr in self.udp_sockets.keys():
            self.udp_unicast(data, addr)
    
    def udp_unicast(self, data, addr):
        payload = data.encode('utf-8')
        self.udp_sockets[addr].sendto(payload, (addr, self.udp_port))

    def parse_parameters(self):
        # should be overridden by subclass
        pass

    def on_connect(self):
        self.subscribe(TOPIC_API_RESPONSE.format(sumo_id=self.sumo_id))
        self.subscribe(TOPIC_DIRECT_COMM.format(sumo_id=self.sumo_id))

    def start_thread(self, method, params=()):
        while not self.client.is_connected():
            time.sleep(0.1)
        thread = KillingThread(target=method, args=params)
        self.threads.append(thread)
        thread.start()

    def join_threads(self):
        for thread in self.threads:
            thread.join()

    @abstractmethod
    def on_start_application(self):
        # this needs to be overridden by child classes
        pass

    @abstractmethod
    def on_stop_application(self):
        # this needs to be overridden by child classes
        pass

    def start_application(self):
        self.start_time = time.time()
        self.on_start_application()

    def stop_application(self):
        self.run = False
        self.on_stop_application()
        self.join_threads()
        self.client.disconnect()
    
    def log_packet(self, source, packet):
        warning(f"Logging received packet {packet.to_json()} from {source} at {time.time()}")
        with self.mutex_logfile:
            self.logfile.write(f"RX_MSG,{time.time()};{source};{packet.to_json()}\n")
            self.logfile.flush()
    
    def log_position(self, pos):
        warning(f"Logging current position {pos}")
        with self.mutex_logfile:
            self.logfile.write(f"POS;{time.time()};{pos}\n")
            self.logfile.flush()


    def transmit(self, destination, packet):
        """ Method used to send a packet through the communication interface
        :param destination: destination node id. TODO: is there something else needed? Is the colosseum_id enough as destination?
        :param packet: data packet to be sent
        """
        if not self.test_mode:
            # TODO: implement this method
            debug(f"Sending broadcast packet via stack from {self.sumo_id} to {destination}: {packet}")
            self.udp_broadcast(packet)
            pass
        else:
            warning(f"Sending packet directly from {self.sumo_id} to {destination}: {packet}")
            self.publish(TOPIC_DIRECT_COMM.format(sumo_id=destination), packet)

    def receive(self, source, packet):
        """ Callback invoked by Colosseum when a packet for this vehicle has been received. This method should be
        overridden by inheriting applications
        :param source: sender node id
        :param packet: received data packet
        """
        pass

    def on_message(self, client, userdata, msg):
        payload = msg.payload.decode()
        debug(f"Received {payload} from {msg.topic} topic")
        if msg.topic == self.topic_api_response:
            message = APIResponseMessage()
            if message.from_json(payload):
                self.__plexe_api_return(message)
        if self.test_mode:
            if msg.topic == TOPIC_DIRECT_COMM.format(sumo_id=self.sumo_id):
                message = VehicleDataMessage()
                if message.from_json(payload):
                    # receive must be called in a thread otherwise if we invoke an API (which uses MQTT) and we stop
                    # waiting for the answer, the MQTT client will also be blocked and won't be able to publish the call
                    receive_thread = KillingThread(target=self.receive, args=(message.sender, message))
                    receive_thread.start()
        

    def call_plexe_api(self, api_code, parameters):
        """ Send via MQTT a Plexe API call. This is basically a blocking RPC call done via MQTT
        :param api_code: API to be called (constants in Plexe.ccparams)
        :param parameters: list of parameters to be passed as a string
        :return result of the call (depending on the API) or None if the call was not successful (e.g., sumo
        has been terminated)
        """
        # get a new transaction id avoiding race conditions
        self.mutex_transaction.acquire(blocking=True)
        transaction_id = self.transaction_id
        self.transaction_id = self.transaction_id + 1
        self.mutex_transaction.release()

        msg = APICallMessage(self.sumo_id, api_code, transaction_id, parameters)
        self.api_semaphores[transaction_id] = Semaphore(0)
        data = msg.to_json()
        # send API call
        debug(f"Sending API call {self.topic_api_call} with content {data}")
        self.publish(self.topic_api_call, data)
        # and block waiting for the result
        debug(f"Blocking caller through semaphore[{transaction_id}]")
        while not self.api_semaphores[transaction_id].acquire(blocking=True, timeout=1):
            # do a blocking call but with a timeout, to enable stopping the thread in case of end of simulation
            if not self.run:
                return None
        # when we pass past the lock, the return value will be set and we can return it to the caller
        return_value = self.api_call_return_value[transaction_id]
        del self.api_call_return_value[transaction_id]
        del self.api_semaphores[transaction_id]
        return return_value

    def __plexe_api_return(self, msg):
        debug(f"API returned {msg.to_json()}")
        # this callback result has not been invoked by this vehicle. ignore it
        if msg.sumo_id != self.sumo_id:
            return
        if msg.transaction_id not in self.api_semaphores.keys():
            error(f"__plexe_api_return: vehicle {self.sumo_id} got api response for transaction {msg.transaction_id}, "
                  f"which does not exist")
            _exit(1)
        # copy return value
        if msg.transaction_id in self.api_call_return_value.keys():
            # safety check!
            error(f"Return value for transaction {msg.transaction_id} already set!")
            _exit(1)
        self.api_call_return_value[msg.transaction_id] = msg.response
        # unlock caller
        debug(f"Unlocking caller waiting for semaphore[{msg.transaction_id}]")
        self.api_semaphores[msg.transaction_id].release()
