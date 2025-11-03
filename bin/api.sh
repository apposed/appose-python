#!/bin/sh
uv run stubgen --include-private -p appose -o api/
uv run stubgen --include-private -o api tests/*.py

# Strip leading import statements -- not needed for
# API comparison with other Appose implementations.
find api -name '*.pyi' | while read pyi
do
  mv "$pyi" "$pyi.original"
  sed -e '/^from /d' -e '/^import /d' "$pyi.original" > "$pyi"
done
