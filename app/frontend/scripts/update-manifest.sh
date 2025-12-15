#!/bin/bash
# Script to update the manifest.json with all tournament files in data/gamestates

GAMESTATES_DIR="$(dirname "$0")/../../data/gamestates"
MANIFEST_FILE="$GAMESTATES_DIR/manifest.json"

# Generate manifest
echo '{"files": [' > "$MANIFEST_FILE"
first=true
for f in "$GAMESTATES_DIR"/tournament_*.json; do
  if [ -f "$f" ]; then
    filename=$(basename "$f")
    if [ "$first" = true ]; then
      first=false
    else
      echo ',' >> "$MANIFEST_FILE"
    fi
    echo -n "  \"$filename\"" >> "$MANIFEST_FILE"
  fi
done
echo '' >> "$MANIFEST_FILE"
echo ']}' >> "$MANIFEST_FILE"

echo "Updated manifest at $MANIFEST_FILE"

