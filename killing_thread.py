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
import traceback
from os import _exit
from sys import stderr
from threading import Thread


class KillingThread(Thread):
    def run(self):
        try:
            super(KillingThread, self).run()
        except Exception as e:
            print(traceback.format_exc())
            print("Exeption in thread:", e, file=stderr)
            _exit(1)
