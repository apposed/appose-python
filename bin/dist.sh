#!/bin/sh

dir=$(dirname "$0")
cd "$dir/.."

python -m build
