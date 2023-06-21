#!/bin/sh

# Usage examples:
#   bin/test.sh
#   bin/test.sh test_appose.py
#   bin/test.sh test_appose.py::test_groovy

set -e

dir=$(dirname "$0")
cd "$dir/.."

if [ $# -gt 0 ]
then
  python -m pytest -p no:faulthandler $@
else
  python -m pytest -p no:faulthandler tests
fi
