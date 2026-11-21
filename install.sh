#!/bin/sh
# orkmem installer. Run it again to update: it replaces the tool, never a memory.
set -e
DIR="$HOME/.orkmem"

python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null || {
  echo "orkmem is one Python file and needs python3 3.11 or newer." >&2
  exit 1
}

mkdir -p "$DIR"
cp "$(dirname "$0")/memo" "$DIR/memo.new"
mv "$DIR/memo.new" "$DIR/memo"
chmod +x "$DIR/memo"
exec "$DIR/memo" init
