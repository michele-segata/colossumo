#!/bin/bash

mkdir ../logs/$1
scp mycolosseum-001:/root/OAI-Colosseum/all_logs.pickle ../logs/$1
scp dev-srn-001:~/git/colosseumo/logs/sumo_positions.dat ../logs/$1

scp mycolosseum-002:/root/colosseumo/logs/p.0.log ../logs/$1
scp mycolosseum-003:/root/colosseumo/logs/p.1.log ../logs/$1
scp mycolosseum-004:/root/colosseumo/logs/p.2.log ../logs/$1