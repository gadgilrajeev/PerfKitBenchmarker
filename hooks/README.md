# README

This folder contains [Git hooks][1] for use in developing PerfKitBenchmarker,
mostly adapted from [kubernetes][2].
Currently they ensure that all Python and shell scripts contain an Apache
2 license header, and that [`flake8`][3] runs without generating lint errors.
Install them by running:

    hooks/install.sh

from the root of the repository. This will symlink the hooks into `.git/hooks/`.

[1]: http://git-scm.com/docs/githooks
[2]: http://github.com/GoogleCloudPlatform/kubernetes
[3]: https://pypi.python.org/pypi/flake8
