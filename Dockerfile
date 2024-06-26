FROM ubuntu:22.04

LABEL Description="Dockerised Simulation of Urban MObility(SUMO)"

#Install SUMO
RUN apt-get update && apt install -y software-properties-common
RUN add-apt-repository ppa:sumo/stable && apt-get update
RUN apt-get install -y sumo sumo-tools sumo-doc
RUN apt-get install -y libxml2-dev libxslt-dev python3-libxml2

#Install Plexe-Pyapi
RUN apt-get install -y git python3-pip
RUN git clone https://github.com/michele-segata/plexe-pyapi.git
RUN cd plexe-pyapi && pip install .   

WORKDIR colossesumo
COPY ./requirements.txt requirements.txt

RUN mkdir -p /sumo
ENV SUMO_HOME /sumo
RUN pip3 install -r requirements.txt

COPY . /colossesumo


CMD python3 colossumo.py --broker $BROKER --port 1883 --config $SUMO_CONFIG --scenario $SUMO_SCENARIO  --application=$SUMO_APP --params=$PARAMS --time $SIM_TIME $EXTRA_ARGS

