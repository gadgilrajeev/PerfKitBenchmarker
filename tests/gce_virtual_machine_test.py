# Copyright 2015 PerfKitBenchmarker Authors. All rights reserved.
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

"""Tests for perfkitbenchmarker.providers.gcp.gce_virtual_machine"""

import contextlib
import mock
import unittest

from perfkitbenchmarker import benchmark_spec
from perfkitbenchmarker import context
from perfkitbenchmarker import errors
from perfkitbenchmarker import vm_util
from perfkitbenchmarker.providers.gcp import gce_virtual_machine
from tests import mock_flags


_COMPONENT = 'test_component'
_FLAGS = None


class MemoryDecoderTestCase(unittest.TestCase):

  def setUp(self):
    super(MemoryDecoderTestCase, self).setUp()
    self.decoder = gce_virtual_machine.MemoryDecoder('memory')

  def testValidStrings(self):
    self.assertEqual(self.decoder.Decode('1280MiB', _COMPONENT, _FLAGS), 1280)
    self.assertEqual(self.decoder.Decode('7.5GiB', _COMPONENT, _FLAGS), 7680)

  def testImproperPattern(self):
    with self.assertRaises(errors.Config.InvalidValue) as cm:
      self.decoder.Decode('1280', _COMPONENT, _FLAGS)
    self.assertEqual(str(cm.exception), (
        'Invalid test_component.memory value: "1280". Examples of valid '
        'values: "1280MiB", "7.5GiB".'))

  def testInvalidFloat(self):
    with self.assertRaises(errors.Config.InvalidValue) as cm:
      self.decoder.Decode('1280.9.8MiB', _COMPONENT, _FLAGS)
    self.assertEqual(str(cm.exception), (
        'Invalid test_component.memory value: "1280.9.8MiB". "1280.9.8" is not '
        'a valid float.'))

  def testNonIntegerMiB(self):
    with self.assertRaises(errors.Config.InvalidValue) as cm:
      self.decoder.Decode('7.6GiB', _COMPONENT, _FLAGS)
    self.assertEqual(str(cm.exception), (
        'Invalid test_component.memory value: "7.6GiB". The specified size '
        'must be an integer number of MiB.'))


class GceVirtualMachineTestCase(unittest.TestCase):

  def setUp(self):
    p = mock.patch(gce_virtual_machine.__name__ +
                   '.gce_network.GceNetwork.GetNetwork')
    self.mock_get_network = p.start()
    self.addCleanup(p.stop)
    p = mock.patch(gce_virtual_machine.__name__ +
                   '.gce_network.GceFirewall.GetFirewall')
    self.mock_get_firewall = p.start()
    self.addCleanup(p.stop)

  def testConstructorNoMachineTypeNoCpus(self):
    spec = gce_virtual_machine.GceVmSpec(_COMPONENT)
    with self.assertRaises(errors.Config.MissingOption) as cm:
      gce_virtual_machine.GceVirtualMachine(spec)
    self.assertEqual(str(cm.exception), (
        'A GCP VM must have either a "machine_type" or both "cpus" and '
        '"memory" configured.'))

  def testConstructorBothMachineTypeAndCpus(self):
    spec = gce_virtual_machine.GceVmSpec(
        _COMPONENT, machine_type='test_machine_type', cpus=1)
    with self.assertRaises(errors.Config.InvalidValue) as cm:
      gce_virtual_machine.GceVirtualMachine(spec)
    self.assertEqual(str(cm.exception), (
        'A GCP VM cannot have both a "machine_type" and either "cpus" or '
        '"memory" configured.'))

  def testVmWithMachineTypeNonPreemptible(self):
    spec = gce_virtual_machine.GceVmSpec(
        _COMPONENT, machine_type='test_machine_type')
    vm = gce_virtual_machine.GceVirtualMachine(spec)
    self.assertEqual(vm.GetMachineTypeDict(), {
        'machine_type': 'test_machine_type'})

  def testVmWithMachineTypePreemptible(self):
    spec = gce_virtual_machine.GceVmSpec(
        _COMPONENT, machine_type='test_machine_type', preemptible=True)
    vm = gce_virtual_machine.GceVirtualMachine(spec)
    self.assertEqual(vm.GetMachineTypeDict(), {
        'machine_type': 'test_machine_type', 'preemptible': True})

  def testCustomVmNonPreemptible(self):
    spec = gce_virtual_machine.GceVmSpec(_COMPONENT, cpus=1, memory='1.0GiB')
    vm = gce_virtual_machine.GceVirtualMachine(spec)
    self.assertEqual(vm.GetMachineTypeDict(), {'cpus': 1, 'memory_mib': 1024})

  def testCustomVmPreemptible(self):
    spec = gce_virtual_machine.GceVmSpec(_COMPONENT, cpus=1, memory='1.0GiB',
                                         preemptible=True)
    vm = gce_virtual_machine.GceVirtualMachine(spec)
    self.assertEqual(vm.GetMachineTypeDict(), {'cpus': 1, 'memory_mib': 1024,
                                               'preemptible': True})


class GCEVMFlagsTestCase(unittest.TestCase):

  def setUp(self):
    # VM Creation depends on there being a BenchmarkSpec.
    self.spec = benchmark_spec.BenchmarkSpec({}, 'name', 'benchmark_uid')
    self.addCleanup(context.SetThreadBenchmarkSpec, None)

  @contextlib.contextmanager
  def _PatchCriticalObjects(self):
    """A context manager that patches a few critical objects with mocks."""
    with mock.patch(vm_util.__name__ + '.IssueCommand') as issue_command, \
            mock.patch('__builtin__.open'), \
            mock.patch(vm_util.__name__ + '.NamedTemporaryFile'), \
            mock_flags.PatchFlags() as mocked_flags:
      mocked_flags.gcloud_path = 'test_gcloud'
      mocked_flags.gcloud_scopes = None
      mocked_flags.run_uri = 'aaaaaa'
      yield issue_command, mocked_flags

  def testPreemptibleVMFlag(self):
    with self._PatchCriticalObjects() as mocked_env:
      issue_command, mocked_flags = mocked_env
      mocked_flags.gce_preemptible_vms = True
      vm_spec = gce_virtual_machine.GceVmSpec(
          'test_vm_spec.GCP', mocked_flags, image='image',
          machine_type='test_machine_type')
      vm = gce_virtual_machine.GceVirtualMachine(vm_spec)
      vm._Create()
      self.assertEquals(issue_command.call_count, 1)
      self.assertIn('--preemptible', issue_command.call_args[0][0])

  def testImageProjectFlag(self):
    """Tests that custom image_project flag is supported."""
    with self._PatchCriticalObjects() as mocked_env:
      issue_command, mocked_flags = mocked_env
      mocked_flags.image_project = 'bar'
      vm_spec = gce_virtual_machine.GceVmSpec(
          'test_vm_spec.GCP', mocked_flags, image='image',
          machine_type='test_machine_type')
      vm = gce_virtual_machine.GceVirtualMachine(vm_spec)
      vm._Create()
      self.assertEquals(issue_command.call_count, 1)
      self.assertIn('--image-project bar',
                    ' '.join(issue_command.call_args[0][0]))


if __name__ == '__main__':
  unittest.main()
