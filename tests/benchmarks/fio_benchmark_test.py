# Copyright 2015 Google Inc. All rights reserved.
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

"""Tests for fio_benchmark."""

import unittest

from perfkitbenchmarker.benchmarks import fio_benchmark


class TestGetIODepths(unittest.TestCase):
  def testOneInteger(self):
    self.assertEqual(list(fio_benchmark.GetIODepths('3')), [3])

  def testIntegerRange(self):
    self.assertEqual(list(fio_benchmark.GetIODepths('3-5')), [3, 4, 5])


class TestGenerateJobFileString(unittest.TestCase):
  def testAgainstDevice(self):
    # This just checks that the template renders.
    fio_benchmark.GenerateJobFileString('/foo', True, '100G', '1-4', 100)

  def testAgainstFile(self):
    fio_benchmark.GenerateJobFileString('/foo', False, '100G', '1-4', 100)


if __name__ == '__main__':
  unittest.main()
