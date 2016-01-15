# Copyright 2014 PerfKitBenchmarker Authors. All rights reserved.
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

"""Container for all data required for a benchmark to run."""

import contextlib
import copy
import copy_reg
import logging
import os
import pickle
import thread
import threading
import uuid

from perfkitbenchmarker import configs
from perfkitbenchmarker import context
from perfkitbenchmarker import disk
from perfkitbenchmarker import errors
from perfkitbenchmarker import flag_util
from perfkitbenchmarker import flags
from perfkitbenchmarker import os_types
from perfkitbenchmarker import provider_info
from perfkitbenchmarker import providers
from perfkitbenchmarker import static_virtual_machine as static_vm
from perfkitbenchmarker import virtual_machine
from perfkitbenchmarker import vm_util


def PickleLock(lock):
  return UnPickleLock, (lock.locked(),)


def UnPickleLock(locked, *args):
  lock = threading.Lock()
  if locked:
    if not lock.acquire(False):
      raise pickle.UnpicklingError('Cannot acquire lock')
  return lock


copy_reg.pickle(thread.LockType, PickleLock)
# Config constants.
VM_GROUPS = 'vm_groups'
CONFIG_FLAGS = 'flags'
DISK_COUNT = 'disk_count'
VM_COUNT = 'vm_count'
DEFAULT_COUNT = 1
CLOUD = 'cloud'
OS_TYPE = 'os_type'
STATIC_VMS = 'static_vms'
VM_SPEC = 'vm_spec'
DISK_SPEC = 'disk_spec'

SUPPORTED = 'strict'
NOT_EXCLUDED = 'permissive'
SKIP_CHECK = 'none'

FLAGS = flags.FLAGS

flags.DEFINE_enum('cloud', providers.GCP,
                  providers.VALID_CLOUDS,
                  'Name of the cloud to use.')
flags.DEFINE_string('scratch_dir', None,
                    'Base name for all scratch disk directories in the VM.'
                    'Upon creation, these directories will have numbers'
                    'appended to them (for example /scratch0, /scratch1, etc).')
flags.DEFINE_enum('benchmark_compatibility_checking', SUPPORTED,
                  [SUPPORTED, NOT_EXCLUDED, SKIP_CHECK],
                  'Method used to check compatibility between the benchmark '
                  ' and the cloud.  ' + SUPPORTED + ' runs the benchmark only'
                  ' if the cloud provider has declared it supported. ' +
                  NOT_EXCLUDED + ' runs the benchmark unless it has been '
                  ' declared not supported by the could provider. ' +
                  SKIP_CHECK + ' does not do the compatibility'
                  ' check. The default is ' + SUPPORTED)


class BenchmarkSpec(object):
  """Contains the various data required to make a benchmark run."""

  def __init__(self, benchmark_config, benchmark_name, benchmark_uid):
    """Initialize a BenchmarkSpec object.

    Args:
      benchmark_config: A Python dictionary representation of the configuration
        for the benchmark. For a complete explanation, see
        perfkitbenchmarker/configs/__init__.py.
      benchmark_name: string. Name of the benchmark.
      benchmark_uid: An identifier unique to this run of the benchmark even
        if the same benchmark is run multiple times with different configs.
    """
    self.config = benchmark_config
    self.name = benchmark_name
    self.uid = benchmark_uid
    self.vms = []
    self.networks = {}
    self.firewalls = {}
    self.networks_lock = threading.Lock()
    self.firewalls_lock = threading.Lock()
    self.vm_groups = {}
    self.deleted = False
    self.file_name = os.path.join(vm_util.GetTempDir(), self.uid)
    self.uuid = str(uuid.uuid4())
    self.always_call_cleanup = False

    # Set the current thread's BenchmarkSpec object to this one.
    context.SetThreadBenchmarkSpec(self)

  @contextlib.contextmanager
  def RedirectGlobalFlags(self):
    """Redirects flag reads and writes to the benchmark-specific flags object.

    Within the enclosed code block, reads and writes to the flags.FLAGS object
    are redirected to a copy that has been merged with config-provided flag
    overrides specific to this benchmark run.
    """
    merged_flags = configs.GetMergedFlags(self.config)
    with flag_util.FlagDictSubstitution(FLAGS, merged_flags.FlagDict):
      yield

  def _GetCloudForGroup(self, group_name):
    """Gets the cloud for a VM group by looking at flags and the config.
    The precedence is as follows (in decreasing order):
      * FLAGS.cloud (if specified on the command line)
      * The "cloud" key in the group config (set by a config override)
      * The "cloud" key in the group config (set by the config file)
      * FLAGS.cloud (the default value)
    """
    group_spec = self.config[VM_GROUPS][group_name]
    if not FLAGS[CLOUD].present and CLOUD in group_spec:
      return group_spec[CLOUD]
    return FLAGS.cloud

  def _GetOsTypeForGroup(self, group_name):
    """Gets the OS type for a VM group by looking at flags and the config.

    The precedence is as follows (in decreasing order):
      * FLAGS.os_type (if specified on the command line)
      * The "os_type" key in the group config (set by a config override)
      * The "os_type" key in the group config (set by the config file)
      * FLAGS.os_type (the default value)
    """
    group_spec = self.config[VM_GROUPS][group_name]
    if not FLAGS[OS_TYPE].present and OS_TYPE in group_spec:
      return group_spec[OS_TYPE]
    return FLAGS.os_type

  def _CheckBenchmarkSupport(self, cloud):
    """ Throw an exception if the benchmark isn't supported."""

    if FLAGS.benchmark_compatibility_checking == SKIP_CHECK:
      return

    provider_info_class = provider_info.GetProviderInfoClass(cloud)
    benchmark_ok = provider_info_class.IsBenchmarkSupported(self.name)
    if FLAGS.benchmark_compatibility_checking == NOT_EXCLUDED:
      if benchmark_ok is None:
        benchmark_ok = True

    if not benchmark_ok:
      raise ValueError('Provider {0} does not support {1}.  Use '
                       '--benchmark_compatibility_checking=none '
                       'to override this check.'.format(
                           provider_info_class.CLOUD,
                           self.name))

  def ConstructVirtualMachines(self):
    """Constructs the BenchmarkSpec's VirtualMachine objects."""
    vm_group_specs = self.config[VM_GROUPS]

    zone_index = 0
    for group_name, group_spec in vm_group_specs.iteritems():
      vms = []
      vm_count = group_spec.get(VM_COUNT, DEFAULT_COUNT)
      if vm_count is None:
        vm_count = FLAGS.num_vms
      disk_count = group_spec.get(DISK_COUNT, DEFAULT_COUNT)

      # First create the Static VMs.
      if STATIC_VMS in group_spec:
        static_vm_specs = group_spec[STATIC_VMS][:vm_count]
        for static_vm_spec_index, spec_kwargs in enumerate(static_vm_specs):
          vm_spec = static_vm.StaticVmSpec(
              '{0}.{1}.{2}.{3}[{4}]'.format(self.name, VM_GROUPS, group_name,
                                            STATIC_VMS, static_vm_spec_index),
              **spec_kwargs)
          static_vm_class = static_vm.GetStaticVmClass(vm_spec.os_type)
          vms.append(static_vm_class(vm_spec))

      os_type = self._GetOsTypeForGroup(group_name)
      cloud = self._GetCloudForGroup(group_name)
      providers.LoadProvider(cloud.lower())

      # This throws an exception if the benchmark is not
      # supported.
      self._CheckBenchmarkSupport(cloud)

      # Then create a VmSpec and possibly a DiskSpec which we can
      # use to create the remaining VMs.
      vm_spec_class = virtual_machine.GetVmSpecClass(cloud)
      vm_spec = vm_spec_class(
          '.'.join((self.name, VM_GROUPS, group_name, VM_SPEC, cloud)),
          FLAGS, **group_spec[VM_SPEC][cloud])

      if DISK_SPEC in group_spec:
        disk_spec_class = disk.GetDiskSpecClass(cloud)
        disk_spec = disk_spec_class(
            '.'.join((self.name, VM_GROUPS, group_name, DISK_SPEC, cloud)),
            FLAGS, **group_spec[DISK_SPEC][cloud])
        # disk_spec.disk_type may contain legacy values that were
        # copied from FLAGS.scratch_disk_type into
        # FLAGS.data_disk_type at the beginning of the run. We
        # translate them here, rather than earlier, because here is
        # where we know what cloud we're using and therefore we're
        # able to pick the right translation table.
        disk_spec.disk_type = disk.WarnAndTranslateDiskTypes(
            disk_spec.disk_type, cloud)
      else:
        disk_spec = None

      # Create the remaining VMs using the specs we created earlier.
      for _ in xrange(vm_count - len(vms)):
        # Assign a zone to each VM sequentially from the --zones flag.
        if FLAGS.zones:
          vm_spec.zone = FLAGS.zones[zone_index]
          zone_index = (zone_index + 1 if zone_index < len(FLAGS.zones) - 1
                        else 0)
        vm = self._CreateVirtualMachine(vm_spec, os_type, cloud)
        if disk_spec:
          vm.disk_specs = [copy.copy(disk_spec) for _ in xrange(disk_count)]
          # In the event that we need to create multiple disks from the same
          # DiskSpec, we need to ensure that they have different mount points.
          if (disk_count > 1 and disk_spec.mount_point):
            for i, spec in enumerate(vm.disk_specs):
              spec.mount_point += str(i)
        vms.append(vm)

      self.vm_groups[group_name] = vms
      self.vms.extend(vms)

  def Prepare(self):
    targets = [(vm.PrepareBackgroundWorkload, (), {}) for vm in self.vms]
    vm_util.RunParallelThreads(targets, len(targets))

  def Provision(self):
    """Prepares the VMs and networks necessary for the benchmark to run."""
    # Sort networks into a guaranteed order of creation based on dict key.
    # There is a finite limit on the number of threads that are created to
    # provision networks. Until support is added to provision resources in an
    # order based on dependencies, this key ordering can be used to avoid
    # deadlock by placing dependent networks later and their dependencies
    # earlier. As an example, AWS stores both per-region and per-zone objects
    # in this dict, and each per-zone object depends on a corresponding
    # per-region object, so the per-region objects are given keys that come
    # first when sorted.
    networks = [self.networks[key] for key in sorted(self.networks.iterkeys())]
    vm_util.RunThreaded(lambda net: net.Create(), networks)

    if self.vms:
      vm_util.RunThreaded(self.PrepareVm, self.vms)
      if FLAGS.os_type != os_types.WINDOWS:
        vm_util.GenerateSSHConfig(self)

  def Delete(self):
    if self.deleted:
      return

    if self.vms:
      try:
        vm_util.RunThreaded(self.DeleteVm, self.vms)
      except Exception:
        logging.exception('Got an exception deleting VMs. '
                          'Attempting to continue tearing down.')

    for firewall in self.firewalls.itervalues():
      try:
        firewall.DisallowAllPorts()
      except Exception:
        logging.exception('Got an exception disabling firewalls. '
                          'Attempting to continue tearing down.')

    for net in self.networks.itervalues():
      try:
        net.Delete()
      except Exception:
        logging.exception('Got an exception deleting networks. '
                          'Attempting to continue tearing down.')
    self.deleted = True

  def StartBackgroundWorkload(self):
    targets = [(vm.StartBackgroundWorkload, (), {}) for vm in self.vms]
    vm_util.RunParallelThreads(targets, len(targets))

  def StopBackgroundWorkload(self):
    targets = [(vm.StopBackgroundWorkload, (), {}) for vm in self.vms]
    vm_util.RunParallelThreads(targets, len(targets))

  def _CreateVirtualMachine(self, vm_spec, os_type, cloud):
    """Create a vm in zone.

    Args:
      vm_spec: A virtual_machine.BaseVmSpec object.
      os_type: The type of operating system for the VM. See the flag of the
          same name for more information.
      cloud: The cloud for the VM. See the flag of the same name for more
          information.
    Returns:
      A virtual_machine.BaseVirtualMachine object.
    """
    vm = static_vm.StaticVirtualMachine.GetStaticVirtualMachine()
    if vm:
      return vm

    vm_class = virtual_machine.GetVmClass(cloud, os_type)
    if vm_class is None:
      raise errors.Error(
          'VMs of type %s" are not currently supported on cloud "%s".' %
          (os_type, cloud))

    return vm_class(vm_spec)

  def PrepareVm(self, vm):
    """Creates a single VM and prepares a scratch disk if required.

    Args:
        vm: The BaseVirtualMachine object representing the VM.
    """
    vm.Create()
    logging.info('VM: %s', vm.ip_address)
    logging.info('Waiting for boot completion.')
    vm.AllowRemoteAccessPorts()
    vm.WaitForBootCompletion()
    vm.AddMetadata(benchmark=self.name, perfkit_uuid=self.uuid,
                   benchmark_uid=self.uid)
    vm.OnStartup()
    if any((spec.disk_type == disk.LOCAL for spec in vm.disk_specs)):
      vm.SetupLocalDisks()
    for disk_spec in vm.disk_specs:
      vm.CreateScratchDisk(disk_spec)

    # This must come after Scratch Disk creation to support the
    # Containerized VM case
    vm.PrepareVMEnvironment()

  def DeleteVm(self, vm):
    """Deletes a single vm and scratch disk if required.

    Args:
        vm: The BaseVirtualMachine object representing the VM.
    """
    if vm.is_static and vm.install_packages:
      vm.PackageCleanup()
    vm.Delete()
    vm.DeleteScratchDisks()

  def PickleSpec(self):
    """Pickles the spec so that it can be unpickled on a subsequent run."""
    with open(self.file_name, 'wb') as pickle_file:
      pickle.dump(self, pickle_file, 2)

  @classmethod
  def GetSpecFromFile(cls, name):
    """Unpickles the spec and returns it.

    Args:
      name: The name of the benchmark (and the name of the pickled file).

    Returns:
      A BenchmarkSpec object.
    """
    file_name = '%s/%s' % (vm_util.GetTempDir(), name)
    try:
      with open(file_name, 'rb') as pickle_file:
        spec = pickle.load(pickle_file)
    except Exception as e:  # pylint: disable=broad-except
      logging.error('Unable to unpickle spec file for benchmark %s.', name)
      raise e
    # Always let the spec be deleted after being unpickled so that
    # it's possible to run cleanup even if cleanup has already run.
    spec.deleted = False
    context.SetThreadBenchmarkSpec(spec)
    return spec
