# ColosSUMO

This application enables running vehicular networking simulations on the Colosseum testbed, enabling to simulate
mobility through SUMO.
The application exploits an MQTT broker to publish data such as vehicle position updates towards Colosseum and to
receive data from Colosseum as well, for example, the content of a packet received through the radio interface.

> [!NOTE]
> The software is currently in its infancy. We are working on the documentation for using the framework together
> with Colosseum. In the meanwhile, you can check the *sample scenario* and the *more realistic scenario*,
> which can both be run without Colosseum.

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
python colossumo.py --broker 127.0.0.1 --port 12345 --config=cfg/freeway.sumo.cfg --scenario=cacc_scenario.CaccScenario --application=application.Application --gui --params=cfg/sim_params.json --test --nodes 10 --time 60
```

The script parameters are the following:

- `--broker`: IP of the broker
- `--port`: port of the broker
- `--config`: SUMO config file
- `--scenario`: python source file implementing the scenario (e.g., adding vehicles and configuring them)
- `--application`: python source file implementing the application, i.e., what needs to be run on each colosseum node
- `--gui`: start SUMO in GUI mode
- `--params`: json file including simulation params, which are passed to the scenario and the application
- `--test`: enable test mode. In this mode the simulation is run without Colosseum, so applications are instantiated
locally by ColosSUMO instead of on Colosseum SRN nodes and communication is fake, emulated via MQTT with a 100%
delivery ratio
- `--nodes`: how many nodes are available in Colosseum for the simulation
- `--time`: maximum simulation time in seconds

## Running a more realistic scenario (without Colosseum)

To run a more realistic scenario but still using test mode (without Colosseum), type

```commandline
python colossumo.py --config=cfg/lust.sumo.cfg --scenario=lust_scenario.LustScenario --gui --application=cacc_application.CACCApplication --params=cfg/sim_params.json --test
```

This scenario simulates a platoon of three vehicles running around the city of Luxembourg.
The leading vehicle continuously changes speed and vehicles exchange control data (see `cacc_application.py`).
To see the effect of missing data, change the `beacon_interval` parameter in `cfg/sim_params.json`.
With 0.1 seconds, the platoon properly maintains inter-vehicle distance.
By setting it to 1 second, you should visually see some distance errors.

## Running using docker

A dockerfile and a docker-compose.yml file are provided to run the ColosseSUMO in a container. However, since SUMO is a gui application some tricks have to be implemented. See [this post](http://wiki.ros.org/docker/Tutorials/GUI)

First of all, run the local dynscen server which cointains the mqtt broker.

Then, enable local access to the X11 server by doing

`xhost +local:root`

Run the ColosseSUMO docker compose file

`docker compose up`

Finally, once you have finished using it restore the X11 auth config

`xhost -local:root`
* `--gui`: start SUMO in gui mode (default false)

## Working principle

ColosSUMO runs a SUMO simulation and sends simulation updates at each step.
Such updates include the current simulation time, the position of the nodes, etc.
Updates are handled through messages, which are published via MQTT in json format.
A single update is an array of messages.
For example, ColosSUMO can send the following update to Colosseum:

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
      "colosseum_id": 0,
      "application": "cacc_application.CACCApplication",
      "parameters": "<json string>"
    }
  },
  {
    "type": "new_vehicle",
    "content": {
      "sumo_id": "p.1",
      "colosseum_id": 1,
      "application": "cacc_application.CACCApplication",
      "parameters": "<json string>"
    }
  },
  {
    "type": "new_vehicle",
    "content": {
      "sumo_id": "p.2",
      "colosseum_id": 2,
      "application": "cacc_application.CACCApplication",
      "parameters": "<json string>"
    }
  },
  {
    "type": "update_position",
    "content": {
      "colosseum_id": 0,
      "x": 291839.0101711491,
      "y": 5498295.976479217,
      "crs": "EPSG:32632"
    }
  },
  {
    "type": "update_position",
    "content": {
      "colosseum_id": 1,
      "x": 291830.67911980435,
      "y": 5498299.379535452,
      "crs": "EPSG:32632"
    }
  },
  {
    "type": "update_position",
    "content": {
      "colosseum_id": 2,
      "x": 291822.34806845966,
      "y": 5498302.782591687,
      "crs": "EPSG:32632"
    }
  }
]
```

The above message tells colosseum:

- The current simulation time
- That some new vehicles have entered the simulation, that they should be associated to Colosseum nodes with given ids,
which application should be run, and what are simulation parameters
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
      "x": 291839.19530562346,
      "y": 5498295.900855745,
      "crs": "EPSG:32632"
    }
  },
  {
    "type": "update_position",
    "content": {
      "colosseum_id": 1,
      "x": 291830.8642542787,
      "y": 5498299.30391198,
      "crs": "EPSG:32632"
    }
  },
  {
    "type": "update_position",
    "content": {
      "colosseum_id": 2,
      "x": 291822.53320293396,
      "y": 5498302.706968215,
      "crs": "EPSG:32632"
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
    "y": "<y coordinate, m>: float",
    "crs": "<coordinate reference system, if present>: string"
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
    "colosseum_id": "<id of colosseum node assigned>: int",
    "application": "<package.ClassName of application to be run>: string",
    "parameters": "<application parameters in json format>: string"
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
    "y": "<y coordinate, m>: float",
    "sender": "<sumo id of the sending vehicle, if this is used as a packet>: string"
  }
}
```

### Start/stop simulation

Direction: Colosseum to SUMO.
After creating vehicles in the simulation ColosSUMO will wait for a signal to start the simulation.
In addition, Colosseum can tell ColosSUMO to stop the SUMO simulation.
```json
{
  "type": "start_simulation",
  "content": {}
}
```
```json
{
  "type": "stop_simulation",
  "content": {}
}
```

### API call message

Direction: Application to SUMO.
This is used by applications to invoke a SUMO/Plexe API, e.g., to obtain data about a vehicle or change its behavior.
API calls are sent via MQTT, and they are synchronously managed using semaphores.
```json
{
  "type": "api_call",
  "content": {
    "sumo_id": "<id of the vehicle calling the api>: string",
    "api_code": "<id of the api>: string",
    "transaction_id": "<id of the call, to identify the answer>: int",
    "parameters": "<parameters to be passed to the api. content is api dependent>: string"
  }
}
```

### API response message

Direction: SUMO to application.
This is used to send the result of an API call to the caller.
```json
{
  "type": "api_return",
  "content": {
    "sumo_id": "<id of the vehicle calling the api>: string",
    "api_code": "<id of the api>: string",
    "transaction_id": "<id of the call, to identify the answer>: int",
    "response": "<return value of the call. content is api dependent>: string"
  }
}
```
