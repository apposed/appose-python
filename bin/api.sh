#!/bin/sh

cd "$(dirname "$0")/.."

# Check for required cross-implementation script.
postprocessScript="../appose/bin/postprocess-api.py"
if [ ! -f "$postprocessScript" ]; then
  echo "Error: $postprocessScript not found" >&2
  echo "Please ensure appose repository is cloned as a sibling directory." >&2
  exit 1
fi

# Clean old API files.
rm -rf api

# Generate pyi API stubs.
uv run stubgen --include-private -p appose -o api/
uv run stubgen --include-private -o api tests/*.py tests/*/*.py

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

# Remove empty files.
find api -size 0 -exec rm "{}" \;

# Rename python_worker.api -> worker.api.
mv api/appose/python_worker.api api/appose/worker.api

# Post-process API: normalize | None to ?, expand optional parameters.
python3 "$postprocessScript" api
