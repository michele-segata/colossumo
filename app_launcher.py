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
from configargparse import ArgumentParser
from importlib import import_module
from logging import basicConfig, DEBUG, WARNING


def main():
    # set debug level
    basicConfig(level=DEBUG)
    parser = ArgumentParser(description="Python script to launch an application on a SRN node", default_config_files=['.env'])
    parser.add_argument("--sumoid", help="SUMO vehicle id")
    parser.add_argument("--colosseumid", help="Colosseum node id", type=int)
    parser.add_argument("--broker", help="IP address of the broker", default="127.0.0.1")
    parser.add_argument("--port", help="Port of the broker", default=12345, type=int)
    parser.add_argument("--params", help="JSON string with simulation params", default="{}")
    parser.add_argument("--application", help="Python application to launch")
    parser.add_argument("--addresses", type=str, action='append', required=False, help="List of unicast addresses")
    args = parser.parse_args()
    sumo_id = args.sumoid
    colosseum_id = args.colosseumid
    broker = args.broker
    port = args.port
    module, class_name = args.application.rsplit(".", 1)
    m = import_module(module)
    application = getattr(m, class_name)
    parameters = args.params
    addresses = args.addresses
    app = application(sumo_id, broker, port, sumo_id, colosseum_id, parameters, False, addresses)
    app.start_application()
    app.join_threads()


if __name__ == "__main__":
    main()
