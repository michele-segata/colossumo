# ColosSeUMO

This application enables running vehicular networking simulations on the Colosseum testbed, enabling to simulate
mobility through SUMO.
The application exploits an MQTT broker to publish data such as vehicle position updates towards Colosseum and to
receive data from Colosseum as well, for example, the content of a packet received through the radio interface.

## Required software

To run ColosSeMO you need to have a running MQTT broker to connect to.
One example is `mosquitto`, which can easily be installed on Linux and macOS systems using one of the following
commands depending on your system:

- `sudo apt install mosquitto`
- `sudo port install mosquitto`
- `sudo brew install mosquitto`

You then need a working copy of SUMO (preferably version 1.18.0).
Follow the [online instructions](https://sumo.dlr.de/docs/Downloads.php) on the official website.
After installing it, ensure SUMO is available through the command line (try running `sumo` in a terminal).
If this does not work, manually add SUMO binaries folder to the `PATH`.
In addition, make sure that the environmental variable `SUMO_HOME`.
Again, visit the [online documentation](https://sumo.dlr.de/docs/Basics/Basic_Computer_Skills.html#sumo_home) for help.

Finally, you will need the Plexe Python APIs.
Simply follow the instructions on the [github repository](https://github.com/michele-segata/plexe-pyapi).

## Running the sample scenario

The sample scenario comprises 4 vehicles travelling in a platoon at constant speed.
To run such scenario, start the broker first.
If you use mosquitto, to start it on port 12345 run:

```commandline
mosquitto -p 12345
```

To start the sample scenario simply type:

```commandline
python colosseumo.py --broker 127.0.0.1 --port 12345 --config cfg/freeway.sumo.cfg --scenario cacc_scenario.CaccScenario --nodes 10 --time 60
```

The script parameters are the following:

- `--broker`: IP of the broker
- `--port`: port of the broker
- `--config`: SUMO config file
- `--scenario`: python source file implementing the scenario (e.g., adding vehicles and configuring them)
- `--nodes`: how many nodes are available in Colosseum for the simulation
- `--time`: maximum simulation time in seconds

## Running using docker

A dockerfile and a docker-compose.yml file are provided to run the ColosseSUMO in a container. However, since SUMO is a gui application some tricks have to be implemented. See [this post](http://wiki.ros.org/docker/Tutorials/GUI)

First of all, run the local dynscen server which cointains the mqtt broker.

Then, enable local access to the X11 server by doing

`xhost +local:root`

Run the ColosseSUMO docker compose file

`docker compose up`

Finally, once you have finished using it restore the X11 auth config

`xhost -local:root`

## Working principle

ColosSeUMO runs a SUMO simulation and sends simulation updates at each step.
Such updates include the current simulation time, the position of the nodes, etc.
Updates are handled through messages, which are published via MQTT in json format.
A single update is an array of messages.
For example, ColosSeUMO can send the following update to Colosseum:

```json
[
  {
    "type": "time",
    "content": {
      "time": 0.01
    }
  },
  {
    "type": "new_vehicle",
    "content": {
      "sumo_id": "p.0",
      "colosseum_id": 0
    }
  },
  {
    "type": "new_vehicle",
    "content": {
      "sumo_id": "p.2",
      "colosseum_id": 1
    }
  },
  {
    "type": "new_vehicle",
    "content": {
      "sumo_id": "p.3",
      "colosseum_id": 2
    }
  },
  {
    "type": "new_vehicle",
    "content": {
      "sumo_id": "p.1",
      "colosseum_id": 3
    }
  },
  {
    "type": "update_position",
    "content": {
      "colosseum_id": 0,
      "x": 99.99999999999999,
      "y": 242.45
    }
  },
  {
    "type": "update_position",
    "content": {
      "colosseum_id": 1,
      "x": 82,
      "y": 242.45
    }
  },
  {
    "type": "update_position",
    "content": {
      "colosseum_id": 2,
      "x": 73,
      "y": 242.45
    }
  },
  {
    "type": "update_position",
    "content": {
      "colosseum_id": 3,
      "x": 91,
      "y": 242.45
    }
  }
]
```

The above message tells colosseum:

- The current simulation time
- That some new vehicles have entered the simulation and they should be associated to Colosseum nodes with given ids
- Where the vehicles are located

In a classic simulation step, the update might simply be like the following:

```json
[
  {
    "type": "time",
    "content": {
      "time": 0.02
    }
  },
  {
    "type": "update_position",
    "content": {
      "colosseum_id": 0,
      "x": 100.25,
      "y": 242.45
    }
  },
  {
    "type": "update_position",
    "content": {
      "colosseum_id": 1,
      "x": 82.25,
      "y": 242.45
    }
  },
  {
    "type": "update_position",
    "content": {
      "colosseum_id": 2,
      "x": 73.25,
      "y": 242.45
    }
  },
  {
    "type": "update_position",
    "content": {
      "colosseum_id": 3,
      "x": 91.24999999999999,
      "y": 242.45
    }
  }
]
```

## List of message types

### Time updates

Direction: SUMO to Colosseum

```json
{
  "type": "time",
  "content": {
    "time": "<simulation time, s>: float"
  }
}
```

### Position updates

Direction: SUMO to Colosseum

```json
{
  "type": "update_position",
  "content": {
    "colosseum_id": "<colosseum node id>: int",
    "x": "<x coordinate, m>: float",
    "y": "<y coordinate, m>: float"
  }
}
```

### New vehicle

Direction: SUMO to Colosseum

```json
{
  "type": "new_vehicle",
  "content": {
    "sumo_id": "<id of vehicle in sumo>: string",
    "colosseum_id": "<id of colosseum node assigned>: int"
  }
}
```

### Vehicle deletion

Direction: SUMO to Colosseum

```json
{
  "type": "delete_vehicle",
  "content": {
    "sumo_id": "<id of vehicle in sumo>: string",
    "colosseum_id": "<id of colosseum node assigned>: int"
  }
}
```

### Vehicle data

Direction: SUMO to Colosseum (colosseum node requesting SUMO own data to be sent)

Direction: Colosseum to SUMO (colosseum informing about reception of a packet)

```json
{
  "type": "vehicle_data",
  "content": {
    "sumo_id": "<id of vehicle in sumo>: string",
    "controller_acceleration": "<vehicle acceleration pre-actuation, m/s/s>: float",
    "acceleration": "<vehicle acceleration, m/s/s>: float",
    "speed": "<vehicle speed, m/s>: float",
    "time": "<simulation time at which data was measured, s>: float",
    "x": "<x coordinate, m>: float",
    "y": "<y coordinate, m>: float"
  }
}
```
