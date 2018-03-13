#!/bin/bash

# Copyright 2018 PerfKitBenchmarker Authors. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.



HPCG_DIR=`pwd`

DATETIME=`hostname`.`date +"%Y%m%d.%H%M%S"`

MPIFLAGS="--mca btl tcp,sm,self"   # just to get rid of warning on psg cluster node wo proper IB sw installed
HPCG_BIN="hpcg"

echo " ****** running HPCG 3-28-17 binary=$HPCG_BIN on $NUM_GPUS GPUs ***************************** "
mpirun {{ ALLOW_RUN_AS_ROOT }} -np $NUM_GPUS $MPIFLAGS -hostfile HOSTFILE $HPCG_DIR/$HPCG_BIN | tee ./results/xhpcg-$DATETIME-output.txt
