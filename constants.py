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

# topic used to send SUMO updates to colosseum
SUMO_UPDATE_TOPIC = "sumo/update"
# topic used to send commands to SUMO from colosseum
COLOSSEUM_UPDATE_TOPIC = "colosseum/update"
# MQTT topics used to send/receive data to/from SUMO
TOPIC_API_PREFIX = "apicall"
TOPIC_API_CALL = f"{TOPIC_API_PREFIX}/{{sumo_id}}"
TOPIC_API_RESPONSE = "apiresponse/{sumo_id}"
# MQTT topic used to send data directly to other vehicles without using the communication stack
TOPIC_DIRECT_COMM = "directcomm/{sumo_id}"

