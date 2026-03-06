#!/bin/sh

dir=$(dirname "$0")
cd "$dir/.."

find target/envs -mindepth 1 -maxdepth 1 -type d | while read d
do
  echo "$d"
  rm -rf "$d"
done
find . -name __pycache__ -type d | while read d
do
  echo "$d"
  rm -rf "$d"
done
rm -rfv .pytest_cache build dist src/*.egg-info target
