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

from json import dumps, loads
from types import SimpleNamespace


class MQTTUpdate:
    """ Class used to combine multiple messages and send them to colosseum
    """
    def __init__(self):
        self.type = "MQTTUpdate"
        self.messages = []

    def add(self, message):
        self.messages.append(message.to_object())

    def to_json(self):
        return dumps({"type": self.type, "messages": self.messages})


class Message:
    """ Generic message class used to send/receive information to/from colosseum. Each message is composed by two
    fields, "type" and "content", for example:
    {
        "type": "update_position",
        "content" : {
            "id": 1,
            "x": 100.3,
            "y": 23.2,
        }
    }
    """
    def __init__(self):
        self.type = ""
        self.content = {}
        self.keys = []

    def set_field(self, name, value):
        setattr(self, name, value)
        self.content[name] = value

    def to_object(self):
        return {
            "type": self.type,
            "content": self.content
        }

    def to_json(self):
        return dumps(self.to_object())

    def from_json(self, json):
        parsed = loads(json, object_hook=lambda d: SimpleNamespace(**d))
        if parsed.type != self.type:
            return False
        else:
            self.content = parsed.content.__dict__
            if not self.check_for_keys():
                return False
            self.from_object()
            return True

    def check_for_keys(self):
        """ Checks that all object keys are present within self.content after importing from json
        """
        for k in self.keys:
            if k not in self.content.keys():
                return False
        return True

    def from_object(self):
        """ To be implemented by inheriting classes to copy values from self.content to class variables after
        importing data from json"""
        pass


class CurrentTimeMessage(Message):
    """ Message to be sent to colosseum to indicate current simulation time
    """
    def __init__(self, time=None):
        super().__init__()
        self.type = "time"
        self.time = time
        self.content = {"time": self.time}
        self.keys = self.content.keys()

    def from_object(self):
        self.time = self.content["time"]


class NewVehicleMessage(Message):
    """ Message to be sent to colosseum to notify about the creation of a new vehicle and the mapping with the node
    """
    def __init__(self, sumo_id=None, colosseum_id=None, application=None, parameters=None):
        super().__init__()
        self.type = "new_vehicle"
        self.sumo_id = sumo_id
        self.colosseum_id = colosseum_id
        self.application = application
        self.parameters = parameters
        self.content = {"sumo_id": self.sumo_id, "colosseum_id": self.colosseum_id, "application": self.application,
                        "parameters": self.parameters}
        self.keys = self.content.keys()

    def from_object(self):
        self.sumo_id = self.content["sumo_id"]
        self.colosseum_id = self.content["colosseum_id"]
        self.application = self.content["application"]
        self.parameters = self.content["parameters"]
        self.timestamp = self.content["timestamp"]


class DeleteVehicleMessage(NewVehicleMessage):
    """ Message to be sent to colosseum to notify about the deletion of a vehicle
    """
    def __init__(self, sumo_id=None, colosseum_id=None):
        super().__init__(sumo_id, colosseum_id)
        self.type = "delete_vehicle"


class PositionUpdateMessage(Message):
    """ Message to be sent to colosseum to notify about the change in position of a vehicle
    """
    def __init__(self, colosseum_id=None, x=None, y=None, crs=""):
        super().__init__()
        self.type = "update_position"
        self.colosseum_id = colosseum_id
        self.x = x
        self.y = y
        self.crs = crs
        self.content = {"colosseum_id": self.colosseum_id, "x": self.x, "y": self.y, "crs": self.crs}
        self.keys = self.content.keys()

    def from_object(self):
        self.colosseum_id = self.content["colosseum_id"]
        self.x = self.content["x"]
        self.y = self.content["y"]


class VehicleDataMessage(Message):
    """ Message used to fetch vehicle data from SUMO by a colosseum node or to set data about another vehicle when a
    packet is received
    """
    def __init__(self, sumo_id=None, controller_acceleration=None, acceleration=None, speed=None, time=None, x=None,
                 y=None, sender=""):
        super().__init__()
        self.type = "vehicle_data"
        self.sumo_id = sumo_id
        self.controller_acceleration = controller_acceleration
        self.acceleration = acceleration
        self.speed = speed
        self.time = time
        self.x = x
        self.y = y
        self.sender = sender
        self.content = {
            "sumo_id": self.sumo_id,
            "controller_acceleration": self.controller_acceleration,
            "acceleration": self.acceleration,
            "speed": self.speed,
            "time": self.time,
            "x": self.x,
            "y": self.y,
            "sender": self.sender,
        }
        self.keys = self.content.keys()

    def from_object(self):
        self.sumo_id = self.content["sumo_id"]
        self.controller_acceleration = self.content["controller_acceleration"]
        self.acceleration = self.content["acceleration"]
        self.speed = self.content["speed"]
        self.time = self.content["time"]
        self.x = self.content["x"]
        self.y = self.content["y"]
        self.sender = self.content["sender"]


class StartSimulationMessage(Message):
    """ Message sent from colosseum to inform we can start moving the vehicles in SUMO
    """
    TYPE = "start_simulation"

    def __init__(self):
        super().__init__()
        self.type = StartSimulationMessage.TYPE
        self.content = {
        }
        self.keys = self.content.keys()


class StopSimulationMessage(Message):
    """ Message sent from colosseum to stop the simulation
    """
    TYPE = "stop_simulation"

    def __init__(self):
        super().__init__()
        self.type = StopSimulationMessage.TYPE
        self.content = {
        }
        self.keys = self.content.keys()


class APICallMessage(Message):
    """ Message sent from colosseum to invoke an API
    """
    TYPE = "api_call"

    def __init__(self, sumo_id=None, api_code=None, transaction_id=None, parameters=None):
        super().__init__()
        self.type = APICallMessage.TYPE
        self.sumo_id = sumo_id
        self.api_code = api_code
        self.transaction_id = transaction_id
        self.parameters = parameters
        self.content = {
            "sumo_id": sumo_id,
            "api_code": api_code,
            "transaction_id": transaction_id,
            "parameters": parameters
        }
        self.keys = self.content.keys()

    def from_object(self):
        self.sumo_id = self.content["sumo_id"]
        self.api_code = self.content["api_code"]
        self.transaction_id = int(self.content["transaction_id"])
        self.parameters = self.content["parameters"]


class APIResponseMessage(Message):
    """ Message sent from Colosseumo to Colosseum to return the response of a remote call
    """
    TYPE = "api_return"

    def __init__(self, sumo_id=None, api_code=None, transaction_id=None, response=None):
        super().__init__()
        self.type = APIResponseMessage.TYPE
        self.sumo_id = sumo_id
        self.api_code = api_code
        self.transaction_id = transaction_id
        self.response = response
        self.content = {
            "sumo_id": sumo_id,
            "api_code": api_code,
            "transaction_id": transaction_id,
            "response": response
        }
        self.keys = self.content.keys()

    def from_object(self):
        self.sumo_id = self.content["sumo_id"]
        self.api_code = self.content["api_code"]
        self.transaction_id = int(self.content["transaction_id"])
        self.response = self.content["response"]
