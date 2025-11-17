#!/bin/sh
uv run stubgen --include-private -p appose -o api/
uv run stubgen --include-private -o api tests/*.py

# Transform .pyi inputs to .api outputs.
# The .api files are merely lightly postprocessed stub files to
# make them easily diffable with other Appose implementations.
find api -name '*.pyi' | while read pyi
do
  sed \
    -e '/^from /d' -e '/^import /d' \
    -e "s/'Task'/Task/g" \
    "$pyi" > "${pyi%.pyi}.api"
  rm "$pyi"
done
