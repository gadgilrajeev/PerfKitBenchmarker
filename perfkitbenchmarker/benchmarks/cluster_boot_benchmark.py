# Copyright 2014 Google Inc. All rights reserved.
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

"""Runs a cluster boot benchmark."""

import logging

from perfkitbenchmarker import flags
from perfkitbenchmarker import vm_util

FLAGS = flags.FLAGS
BENCHMARK_INFO = {'name': 'cluster boot',
                  'description': 'Create a cluster, record all times to boot',
                  'scratch_disk': False,
                  'num_machines': None}  # Set in GetInfo()


def GetInfo():
  BENCHMARK_INFO['num_machines'] = FLAGS.num_vms
  return BENCHMARK_INFO


def Prepare(unused_benchmark_spec):
  pass


def _GetTimeToBoot(vm, vm_index, result_list):
  metadata = {'machine_type': vm.machine_type, 'num_cpus': vm.num_cpus,
              'machine_instance': vm_index}
  value = vm.TimeToBoot()
  assert value is not None
  result_list.append(('Boot Time', value, 'seconds', metadata))


def Run(benchmark_spec):
  """Measure the boot time for all VMs.

  Args:
    benchmark_spec: The benchmark specification. Contains all data that is
        required to run the benchmark.

  Returns:
    A list of samples in the form of 3 or 4 tuples. The tuples contain
        the sample metric (string), value (float), and unit (string).
        If a 4th element is included, it is a dictionary of sample
        metadata.
  """

  samples = []
  logging.info('Boot Results:')
  vms = benchmark_spec.vms
  params = [((vm, i, samples), {}) for i, vm in enumerate(vms)]
  vm_util.RunThreaded(_GetTimeToBoot, params)
  logging.info(samples)
  assert len(samples) == benchmark_spec.num_vms
  return samples


def Cleanup(unused_benchmark_spec):
  pass
