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


from plexe import ACC, CACC

from scenario import Scenario
from utils import add_platooning_vehicle


class CaccScenario(Scenario):
    def __init__(self, traci, plexe):
        super().__init__(traci, plexe)
        self.add_vehicles(4, 100, 25, 4, 5)

    def add_vehicles(self, n, position, speed, length, distance):
        """
        Adds a platoon of n vehicles to the simulation, plus an additional one
        farther away that wants to join the platoon
        :param n: number of vehicles of the platoon
        :param position: position of the leader
        :param speed: injection speed
        :param length: length of a single car
        :param distance: distance between two consecutive cars
        """
        # add a platoon of n vehicles
        plexe = self.plexe
        traci = self.traci
        leader = ""
        for i in range(n):
            vid = "p.%d" % i
            add_platooning_vehicle(plexe, vid, position - i * (distance + length), 0, speed, distance, False)
            plexe.set_fixed_lane(vid, 0, safe=True if i == 0 else False)
            traci.vehicle.setSpeedMode(vid, 0)
            if i == 0:
                plexe.set_active_controller(vid, ACC)
                plexe.enable_auto_lane_changing(vid, True)
                leader = vid
            else:
                plexe.set_active_controller(vid, CACC)
                plexe.enable_auto_feed(vid, True, leader, "p.%d" % (i-1))
                plexe.add_member(leader, vid, i)
        traci.gui.trackVehicle("View #0", leader)
        traci.gui.setZoom("View #0", 50000)
