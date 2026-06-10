#!/bin/bash
# Rebuild all .app files to point to the current directory.
# Run this from ~/streamdeck on the Mac.

DIR="$(cd "$(dirname "$0")" && pwd)"

for sh in "$DIR"/*.sh; do
  name="$(basename "$sh" .sh)"
  app="$DIR/$name.app"
  echo "Building $name.app ..."
  osacompile -o "$app" -e "do shell script \"$sh\""
done

echo "Done."
