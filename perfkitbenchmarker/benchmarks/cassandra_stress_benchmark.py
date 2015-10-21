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

"""Runs cassandra.

Cassandra homepage: http://cassandra.apache.org
cassandra-stress tool page:
http://www.datastax.com/documentation/cassandra/2.0/cassandra/tools/toolsCStress_t.html
"""

import collections
import functools
import logging
import math
import os
import posixpath
import re
import time


from perfkitbenchmarker import configs
from perfkitbenchmarker import errors
from perfkitbenchmarker import flags
from perfkitbenchmarker import regex_util
from perfkitbenchmarker import sample
from perfkitbenchmarker import vm_util
from perfkitbenchmarker.packages import cassandra


NUM_KEYS_PER_CORE = 2000000

flags.DEFINE_integer('num_keys', 0,
                     'Number of keys used in cassandra-stress tool. '
                     'If unset, this benchmark will use %s * num_cpus '
                     'on data nodes as the value.' % NUM_KEYS_PER_CORE)

flags.DEFINE_integer('num_cassandra_stress_threads', 50,
                     'Number of threads used in cassandra-stress tool '
                     'on each loader node.')

FLAGS = flags.FLAGS

BENCHMARK_NAME = 'cassandra_stress'
BENCHMARK_CONFIG = """
cassandra_stress:
  description: Benchmark Cassandra using cassandra-stress
  vm_groups:
    cassandra_nodes:
      vm_spec: *default_single_core
      disk_spec: *default_500_gb
      vm_count: 3
    stress_client:
      vm_spec: *default_single_core
"""

CASSANDRA_GROUP = 'cassandra_nodes'
CLIENT_GROUP = 'stress_client'

PROPAGATION_WAIT_TIME = 30
SLEEP_BETWEEN_CHECK_IN_SECONDS = 5


# Stress test options.
CONSISTENCY_LEVEL = 'QUORUM'
REPLICATION_FACTOR = 3
RETRIES = 1000

CASSANDRA_STRESS = posixpath.join(cassandra.CASSANDRA_DIR, 'tools', 'bin',
                                  'cassandra-stress')
RESULTS_METRICS = ['op rate', 'partition rate', 'row rate', 'latency mean',
                   'latency median', 'latency 95th percentile',
                   'latency 99th percentile', 'latency 99.9th percentile',
                   'latency max', 'Total operation time']
AGGREGATED_METRICS = ['op rate', 'partition rate', 'row rate']
MAXIMUM_METRICS = ['latency max']


def GetConfig(user_config):
  return configs.LoadConfig(BENCHMARK_CONFIG, user_config, BENCHMARK_NAME)


def CheckPrerequisites():
  """Verifies that the required resources are present.

  Raises:
    perfkitbenchmarker.data.ResourceNotFound: On missing resource.
  """
  cassandra.CheckPrerequisites()


def Prepare(benchmark_spec):
  """Install Cassandra and Java on target vms.

  Args:
    benchmark_spec: The benchmark specification. Contains all data that is
        required to run the benchmark.
  """
  vm_dict = benchmark_spec.vm_groups
  cassandra_vms = vm_dict[CASSANDRA_GROUP]
  logging.info('VM dictionary %s', vm_dict)

  logging.info('Authorizing loader[0] permission to access all other vms.')
  vm_dict[CLIENT_GROUP][0].AuthenticateVm()

  logging.info('Preparing data files and Java on all vms.')
  vm_util.RunThreaded(lambda vm: vm.Install('cassandra'), benchmark_spec.vms)
  seed_vm = cassandra_vms[0]
  configure = functools.partial(cassandra.Configure, seed_vms=[seed_vm])
  vm_util.RunThreaded(configure, cassandra_vms)
  cassandra.StartCluster(seed_vm, cassandra_vms[1:])


def _ResultFilePath(vm):
  return posixpath.join(vm_util.VM_TMP_DIR,
                        vm.hostname + '.stress_results.txt')


def RunTestOnLoader(vm, data_node_ips):
  """Run Cassandra-stress test on loader node.

  Args:
    vm: The target vm.
    data_node_ips: List of IP addresses for all data nodes.
  """
  vm.RobustRemoteCommand(
      '%s write n=%s cl=%s '
      '-node %s -schema replication\(factor=%s\) '
      '-log file=%s -rate threads=%s -errors retries=%s' % (
          CASSANDRA_STRESS, FLAGS.num_keys, CONSISTENCY_LEVEL,
          ','.join(data_node_ips), REPLICATION_FACTOR,
          _ResultFilePath(vm), RETRIES, FLAGS.num_cassandra_stress_threads))


def RunCassandraStress(benchmark_spec):
  """Start Cassandra test.

  Args:
    benchmark_spec: The benchmark specification. Contains all data
        that is required to run the benchmark.
  """
  logging.info('Creating Keyspace.')
  loader_vms = benchmark_spec.vm_groups[CLIENT_GROUP]
  cassandra_vms = benchmark_spec.vm_groups[CASSANDRA_GROUP]
  data_node_ips = [vm.internal_ip for vm in cassandra_vms]

  loader_vms[0].RemoteCommand(
      '%s write n=1 cl=%s '
      '-node %s -schema replication\(factor=%s\) > /dev/null' % (
          CASSANDRA_STRESS, CONSISTENCY_LEVEL,
          ','.join(data_node_ips), REPLICATION_FACTOR))
  logging.info('Waiting %s for keyspace to propagate.', PROPAGATION_WAIT_TIME)
  time.sleep(PROPAGATION_WAIT_TIME)

  if not FLAGS.num_keys:
    FLAGS.num_keys = NUM_KEYS_PER_CORE * cassandra_vms[0].num_cpus
    logging.info('Num keys not set, using %s in cassandra-stress test.',
                 FLAGS.num_keys)
  logging.info('Executing the benchmark.')
  args = [((loader_vm, data_node_ips), {}) for loader_vm in loader_vms]
  vm_util.RunThreaded(RunTestOnLoader, args)


def WaitForLoaderToFinish(vm):
  """Watch loader node and wait for it to finish test.

  Args:
    vm: The target vm.
  """
  result_path = _ResultFilePath(vm)
  while True:
    resp, _ = vm.RemoteCommand('tail -n 1 ' + result_path)
    if re.findall(r'END', resp):
      break
    if re.findall(r'FAILURE', resp):
      vm.PullFile(vm_util.GetTempDir(), result_path)
      raise errors.Benchmarks.RunError(
          'cassandra-stress tool failed, check %s for details.'
          % posixpath.join(vm_util.GetTempDir(),
                           os.path.basename(result_path)))
    time.sleep(SLEEP_BETWEEN_CHECK_IN_SECONDS)


def CollectResultFile(vm, results):
  """Collect result file on vm.

  Args:
    vm: The target vm.
    results: A dictionary of lists. Each list contains results of a field defined in
        RESULTS_METRICS collected from each loader machines.
  """
  result_path = _ResultFilePath(vm)
  vm.PullFile(vm_util.GetTempDir(), result_path)
  resp, _ = vm.RemoteCommand('tail -n 20 ' + result_path)
  for metric in RESULTS_METRICS:

    try:
      value = regex_util.ExtractGroup(r'%s[\t ]+: ([\d\.:]+)' % metric, resp)
      if metric == RESULTS_METRICS[-1]:  # Total operation time
        value = value.split(':')
        results[metric].append(
            int(value[0]) * 3600 + int(value[1]) * 60 + int(value[2]))
      else:
        results[metric].append(float(value))
    except regex_util.NoMatchError:
      logging.exception('No value for %s', metric)


def RunCassandraStressTest(benchmark_spec):
  """Start all loader nodes as Cassandra clients and run stress test.

  Args:
    benchmark_spec: The benchmark specification. Contains all data
        that is required to run the benchmark.
  """
  try:
    RunCassandraStress(benchmark_spec)
  finally:
    logging.info('Tests running. Watching progress.')
    vm_util.RunThreaded(WaitForLoaderToFinish,
                        benchmark_spec.vm_groups[CLIENT_GROUP])


def CollectResults(benchmark_spec):
  """Collect and parse test results.

  Args:
    benchmark_spec: The benchmark specification. Contains all data
        that is required to run the benchmark.

  Returns:
    A list of sample.Sample objects.
  """
  logging.info('Gathering results.')
  vm_dict = benchmark_spec.vm_groups
  loader_vms = vm_dict[CLIENT_GROUP]
  raw_results = collections.defaultdict(list)
  args = [((vm, raw_results), {}) for vm in loader_vms]
  vm_util.RunThreaded(CollectResultFile, args)

  metadata = {'num_keys': FLAGS.num_keys,
              'num_data_nodes': len(vm_dict[CASSANDRA_GROUP]),
              'num_loader_nodes': len(loader_vms),
              'num_cassandra_stress_threads':
              FLAGS.num_cassandra_stress_threads}
  results = []
  for metric in RESULTS_METRICS:
    if metric in MAXIMUM_METRICS:
      value = max(raw_results[metric])
    else:
      value = math.fsum(raw_results[metric])
      if metric not in AGGREGATED_METRICS:
        value = value / len(loader_vms)
    if metric.startswith('latency'):
      unit = 'ms'
    elif metric.endswith('rate'):
      unit = 'operations per second'
    elif metric == 'Total operation time':
      unit = 'seconds'
    results.append(sample.Sample(metric, value, unit, metadata))
  logging.info('Cassandra results:\n%s', results)
  return results


def Run(benchmark_spec):
  """Run Cassandra on target vms.

  Args:
    benchmark_spec: The benchmark specification. Contains all data
        that is required to run the benchmark.

  Returns:
    A list of sample.Sample objects.
  """
  RunCassandraStressTest(benchmark_spec)
  return CollectResults(benchmark_spec)


def Cleanup(benchmark_spec):
  """Cleanup function.

  Args:
    benchmark_spec: The benchmark specification. Contains all data
        that is required to run the benchmark.
  """
  vm_dict = benchmark_spec.vm_groups
  cassandra_vms = vm_dict[CASSANDRA_GROUP]

  vm_util.RunThreaded(cassandra.Stop, cassandra_vms)
  vm_util.RunThreaded(cassandra.CleanNode, cassandra_vms)
