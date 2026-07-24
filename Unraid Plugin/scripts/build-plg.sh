#!/bin/sh
# Build gsmnode.plg from source/.
#
# The plugin is one self-contained file: Unraid installs it straight from a URL,
# with nothing else to fetch and no package to host. The agent definition and
# its icon ride along base64-encoded, because the definition is itself XML with
# a CDATA section in it and XML cannot nest one CDATA section inside another.
#
# Run from anywhere:  sh "Unraid Plugin/scripts/build-plg.sh" [output path]
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_dir="$here/source"
out="${1:-$here/gsmnode.plg}"

for f in gsmnode.plg.in gsmnode.xml gsmnode.png; do
  [ -f "$source_dir/$f" ] || { echo "missing $source_dir/$f" >&2; exit 1; }
done

# The definition has to survive the round trip through the flash drive as LF —
# a stray CR would end up in the agent script the webGUI writes out.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
tr -d '\r' < "$source_dir/gsmnode.xml" | base64 > "$tmp/xml.b64"
base64 < "$source_dir/gsmnode.png" > "$tmp/png.b64"

# sed's `r` reads a file in after the matching line; the `d` then drops the
# placeholder itself. Doing it this way keeps the blobs out of the shell, where
# a 9KB argument list is asking for trouble.
sed \
  -e "/@AGENT_XML_BASE64@/r $tmp/xml.b64" -e "/@AGENT_XML_BASE64@/d" \
  -e "/@AGENT_ICON_BASE64@/r $tmp/png.b64" -e "/@AGENT_ICON_BASE64@/d" \
  "$source_dir/gsmnode.plg.in" | tr -d '\r' > "$out"

if grep -q '@[A-Z_]*BASE64@' "$out"; then
  echo "a placeholder was left unfilled in $out" >&2
  exit 1
fi

version=$(sed -n 's/.*<!ENTITY *version *"\([^"]*\)".*/\1/p' "$out")
echo "built $out (version ${version:-unknown}, $(wc -c < "$out") bytes)"
