#!/bin/sh

# Usage examples:
#   bin/test.sh
#   bin/test.sh test_appose.py
#   bin/test.sh test_appose.py::test_groovy

set -e

dir=$(dirname "$0")
cd "$dir/.."

if [ ! -d target/dependency ]
then
  echo "==> Installing appose-java..."
  mvn -f appose.pom dependency:copy-dependencies
fi

if [ $# -gt 0 ]
then
  uv run python -m pytest -v -p no:faulthandler $@
else
  uv run python -m pytest -v -p no:faulthandler tests
fi
