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

"""Runs all benchmarks in PerfKitBenchmarker.

All benchmarks in PerfKitBenchmarker export the following interface:

GetInfo: this returns, the name of the benchmark, the number of mahcines
          required to run one instance of the benchmark, a detailed description
          of the benchmark, and if the benchmark requires a scratch disk.
Prepare: this function takes a list of VMs as an input parameter. The benchmark
         will then get all binaries required to run the benchmark and, if
         required, create data files.
Run: this function takes a list of VMs as an input parameter. The benchmark will
     then run the benchmark upon the machines specified. The function will
     return a dictonary containing the results of the benchmark.
Cleanup: this function takes a list of VMs as an input parameter. The benchmark
         will then return the machine to the state it was at before Prepare
         was called.

PerfKitBenchmarker has following run stages: prepare, run, cleanup and all.
prepare: PerfKitBenchmarker will read command-line flags, decide which
benchmarks to run
         and create necessary resources for each benchmark, including networks,
         VMs, disks, keys and execute the Prepare function of each benchmark to
         install necessary softwares, upload datafiles, etc and generate a
         run_uri, which can be used to run benchmark multiple times.
run: PerfKitBenchmarker execute the Run function of each benchmark and collect
samples
     generated. Publisher may publish these samples accourding to settings. Run
     stage can be called multiple times with the run_uri generated by prepare
     stage.
cleanup: PerfKitBenchmarker will run Cleanup function of each benchmark to
uninstall
         softwares and delete data files. Then it will delete VMs, key files,
         networks, disks generated in prepare stage.
all: PerfKitBenchmarker will run all above stages (prepare, run, cleanup). Any
resources
     generated in prepare will be automatically deleted at last.
     PerfKitBenchmarker won't
     be able to rerun with exactly same VMs, networks, disks with the same
     run_uri.
"""

import getpass
import logging
import sys
import time
import uuid

import gflags as flags

from perfkitbenchmarker import benchmarks
from perfkitbenchmarker import benchmark_spec
from perfkitbenchmarker import static_virtual_machine
from perfkitbenchmarker import version
from perfkitbenchmarker import vm_util
from perfkitbenchmarker.publisher import PerfKitBenchmarkerPublisher

STAGE_ALL = 'all'
STAGE_PREPARE = 'prepare'
STAGE_RUN = 'run'
STAGE_CLEANUP = 'cleanup'
DEBUG = 'debug'
INFO = 'info'
LOG_LEVELS = {
    DEBUG: logging.DEBUG,
    INFO: logging.INFO
}
REQUIRED_INFO = ['scratch_disk', 'num_machines']
FLAGS = flags.FLAGS

flags.DEFINE_list('ssh_options', [], 'Additional options to pass to ssh.')
flags.DEFINE_integer('parallelism', 1,
                     'The number of benchmarks to run in parallel.')
flags.DEFINE_list('benchmarks', [], 'Benchmarks that should be run, '
                  'default is all.')
# TODO(user): Remove this. It is here to make my life easier for the moment.
flags.DEFINE_string('project', 'bionic-baton-343', 'Project name under which '
                    'to create the virtual machines')
flags.DEFINE_list(
    'zones', None,
    'A list of zones within which to run PerfKitBenchmarker.'
    ' This is specific to the cloud provider you are running on. '
    'If multiple zones are given, PerfKitBenchmarker will create 1 VM in '
    'zone, until enough VMs are created as specified in each '
    'benchmark.')
# TODO(user): note that this is currently very GCE specific. Need to create a
#    module which can traslate from some generic types to provider specific
#    nomenclature.
flags.DEFINE_string('machine_type', None, 'Machine '
                    'types that will be created for benchmarks that don\'t '
                    'require a particular type.')
flags.DEFINE_integer('num_vms', 1, 'For benchmarks which can make use of a '
                     'variable number of machines, the number of VMs to use.')
flags.DEFINE_string('image', None, 'Default image that will be '
                    'linked to the VM')
flags.DEFINE_integer('scratch_disk_size', 500, 'Size, in gb, for all scratch '
                     'disks, default is 500')
flags.DEFINE_string('scratch_disk_type', benchmark_spec.STANDARD, 'Type, in '
                    'string, for all scratch disks, default is standard')
flags.DEFINE_string('run_uri', None, 'Name of the Run. If provided, this '
                    'should be alphanumeric and less than or equal to 10 '
                    'characters in length.')
flags.DEFINE_string('owner', getpass.getuser(), 'Owner name. '
                    'Used to tag created resources and performance records.')
flags.DEFINE_enum('log_level', INFO, [DEBUG, INFO], 'The log level to run at.')
flags.DEFINE_enum(
    'run_stage', STAGE_ALL,
    [STAGE_ALL, STAGE_PREPARE, STAGE_RUN, STAGE_CLEANUP],
    'The stage of perfkitbenchmarker to run. By default it runs all stages.')
flags.DEFINE_list('benchmark_config_pair', None,
                  'Benchmark and its config file pair, separated by :.')
flags.DEFINE_integer('duration_in_seconds', None,
                     'duration of benchmarks. '
                     '(only valid for mesh_benchmark)')
flags.DEFINE_string('static_vm_file', None,
                    'The file path for the Static Machine file. See '
                    'static_virtual_machine.py for a description of this file.')
flags.DEFINE_boolean('version', False, 'Display the version and exit.')

MAX_RUN_URI_LENGTH = 10


def ConfigureLogging():
  """Configure logging.

  Note that this will destroy existing logging configuration!

  This configures python logging with a pair of handlers:
  * Messages at FLAGS.log_level and above are emitted to stderr.
  * Messages at DEBUG and above are emitted to 'pkb.log' under
    vm_util.GetTempDir().
  """
  logger = logging.getLogger()
  logger.handlers = []
  logger.setLevel(logging.DEBUG)

  stream_handler = logging.StreamHandler()
  stream_handler.setLevel(LOG_LEVELS[FLAGS.log_level])
  formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
  stream_handler.setFormatter(formatter)
  logger.addHandler(stream_handler)

  vm_util.GenTempDir()
  log_path = vm_util.PrependTempDir('pkb.log')
  logging.info('Verbose logging to: %s', log_path)
  file_handler = logging.FileHandler(filename=log_path)
  file_handler.setLevel(logging.DEBUG)
  formatter = logging.Formatter(
      '%(asctime)s %(filename)s:%(lineno)d %(levelname)-8s %(message)s')
  file_handler.setFormatter(formatter)
  logger.addHandler(file_handler)


def ShouldRunBenchmark(benchmark):
  if not FLAGS.benchmarks:
    return True
  return benchmark['name'] in FLAGS.benchmarks


# TODO(user): Consider moving to benchmark_spec.
def ValidateBenchmarkInfo(benchmark_info):
  for required_key in REQUIRED_INFO:
    if required_key not in benchmark_info:
      logging.error('Benchmark information %s is corrupt. It does not contain'
                    'the key %s. Please add the specified key to the benchmark'
                    'info. Skipping benchmark.', benchmark_info, required_key)
      # TODO(user): Raise error with info about the validation failure
      return False
  return True


def ListUnknownBenchmarks():
  """Identify invalid benchmark names specified in the command line flags."""
  valid_benchmark_names = frozenset(benchmark.GetInfo()['name']
                                    for benchmark in benchmarks.BENCHMARKS)
  specified_benchmark_names = frozenset(FLAGS.benchmarks)

  return sorted(specified_benchmark_names - valid_benchmark_names)


def RunBenchmark(benchmark, publisher):
  """Runs a single benchmark and adds the results to the publisher.

  Args:
    benchmark: The benchmark module to be run.
    publisher: The PerfKitBenchmarkerPublisher object to add samples to.
  """
  benchmark_info = benchmark.GetInfo()
  benchmark_specification = None
  if not ShouldRunBenchmark(benchmark_info):
    return
  if not ValidateBenchmarkInfo(benchmark_info):
    return
  start_time = time.time()
  try:
    if FLAGS.run_stage in [STAGE_ALL, STAGE_PREPARE]:
      logging.info('Preparing benchmark %s', benchmark_info['name'])
      benchmark_specification = benchmark_spec.BenchmarkSpec(benchmark_info)
      benchmark_specification.Prepare()
      benchmark.Prepare(benchmark_specification)
    else:
      benchmark_specification = benchmark_spec.BenchmarkSpec.GetSpecFromFile(
          benchmark_info['name'])
    if FLAGS.run_stage in [STAGE_ALL, STAGE_RUN]:
      logging.info('Running benchmark %s', benchmark_info['name'])
      samples = benchmark.Run(benchmark_specification)
      publisher.AddSamples(samples, benchmark_info['name'],
                           benchmark_specification)

    if FLAGS.run_stage in [STAGE_ALL, STAGE_CLEANUP]:
      logging.info('Cleaning up benchmark %s', benchmark_info['name'])
      benchmark.Cleanup(benchmark_specification)
      benchmark_specification.Delete()
      if FLAGS.run_stage == STAGE_ALL:
        end_time = time.time()
        end_to_end_sample = ['End to End Runtime',
                             end_time - start_time,
                             'seconds', {}]
        publisher.AddSamples([end_to_end_sample], benchmark_info['name'],
                             benchmark_specification)
  except Exception:
    # Resource cleanup (below) can take a long time. Log the error to give
    # immediate feedback, then re-throw.
    logging.exception('Error during benchmark %s', benchmark_info['name'])
    raise
  finally:
    if FLAGS.run_stage in [STAGE_ALL, STAGE_CLEANUP]:
      if benchmark_specification:
        benchmark_specification.Delete()
    else:
      benchmark_specification.PickleSpec()


def RunBenchmarks(publish=True):
  """Runs all benchmarks in PerfKitBenchmarker.

  Args:
    publish: A boolean indicating whether results should be published.

  Returns:
    Exit status for the process.
  """
  if FLAGS.version:
    print version.VERSION
    return

  if FLAGS.run_uri is None:
    if FLAGS.run_stage not in [STAGE_ALL, STAGE_PREPARE]:
      logging.error(
          'Cannot run "%s" with unspecified run_uri.', FLAGS.run_stage)
      return 1
    else:
      FLAGS.run_uri = str(uuid.uuid4())[-8:]
  elif not FLAGS.run_uri.isalnum() or len(FLAGS.run_uri) > MAX_RUN_URI_LENGTH:
    logging.error('run_uri must be alphanumeric and less than or equal '
                  'to 10 characters in length.')
    return 1

  ConfigureLogging()

  unknown_benchmarks = ListUnknownBenchmarks()
  if unknown_benchmarks:
    logging.error('Unknown benchmark(s) provided: %s',
                  ', '.join(unknown_benchmarks))
    return 1

  vm_util.SSHKeyGen()
  publisher = PerfKitBenchmarkerPublisher()

  if FLAGS.static_vm_file:
    with open(FLAGS.static_vm_file) as fp:
      static_virtual_machine.StaticVirtualMachine.ReadStaticVirtualMachineFile(
          fp)

  if FLAGS.benchmark_config_pair:
    # Convert benchmark_config_pair into a {benchmark_name: file_name}
    # dictionary.
    tmp_dict = {}
    for config_pair in FLAGS.benchmark_config_pair:
      pair = config_pair.split(':')
      tmp_dict[pair[0]] = pair[1]
    FLAGS.benchmark_config_pair = tmp_dict

  try:
    if FLAGS.parallelism > 1:
      args = [((benchmark, publisher), {})
              for benchmark in benchmarks.BENCHMARKS]
      vm_util.RunThreaded(
          RunBenchmark, args, max_concurrent_threads=FLAGS.parallelism)
    else:
      for benchmark in benchmarks.BENCHMARKS:
        RunBenchmark(benchmark, publisher)
  finally:
    if publisher.samples:
      publisher.WriteFile()
      publisher.DumpData()
      publisher.PrettyPrintData()
      if publish:
        publisher.PublishData()

  if FLAGS.run_stage not in [STAGE_ALL, STAGE_CLEANUP]:
    logging.info(
        'To run again with this setup, please use --run_uri=%s', FLAGS.run_uri)


def Main(argv=sys.argv):
  logging.basicConfig(level=logging.INFO)
  # TODO: Verify if there is other way of appending additional help
  # message.
  # Inject more help documentation
  benchmark_list = ['%s:  %s' % (benchmark_module.GetInfo()['name'],
                                 benchmark_module.GetInfo()['description'])
                    for benchmark_module in benchmarks.BENCHMARKS]
  sys.modules['__main__'].__doc__ = __doc__ + (
      '\nBenchmarks:\n\t%s') % '\n\t'.join(benchmark_list)
  try:
    argv = FLAGS(argv)  # parse flags
  except flags.FlagsError as e:
    logging.error(
        '%s\nUsage: %s ARGS\n%s', e, sys.argv[0], FLAGS)
    sys.exit(1)
  return RunBenchmarks()
