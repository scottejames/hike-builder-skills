#!/usr/bin/env bash
# Install the hikeBuilder skills into a workspace folder (default: ~/hiking).
#   ./install.sh [WORKSPACE]
# Creates symlinks back to this repo, so `git pull` here updates every workspace:
#   WORKSPACE/hike-kit                  -> REPO/hike-kit
#   WORKSPACE/.claude/skills/<skill>    -> REPO/skills/<skill>
# and creates your private files (never committed):
#   WORKSPACE/.env             API keys (mode 600), from hike-kit/env.example
#   WORKSPACE/known-huts.yaml  scout huts you can use, from hike-kit/known-huts.example.yaml
set -euo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
WS="${1:-$HOME/hiking}"
mkdir -p "$WS/.claude/skills"
WS="$(cd "$WS" && pwd)"

link() {  # link SRC DST, replacing an old symlink but never a real file or folder
  if [ -L "$2" ]; then ln -sfn "$1" "$2"
  elif [ -e "$2" ]; then echo "  skip: $2 exists and is not a symlink"; return
  else ln -s "$1" "$2"; fi
  echo "  linked $2"
}
echo "Workspace: $WS"
link "$REPO/hike-kit" "$WS/hike-kit"
for s in "$REPO"/skills/*/; do s="${s%/}"; link "$s" "$WS/.claude/skills/$(basename "$s")"; done

if [ ! -e "$WS/.env" ]; then
  (umask 077; cp "$REPO/hike-kit/env.example" "$WS/.env"); echo "  created $WS/.env - add your API keys"
fi
if [ ! -e "$WS/known-huts.yaml" ]; then
  cp "$REPO/hike-kit/known-huts.example.yaml" "$WS/known-huts.yaml"; echo "  created $WS/known-huts.yaml"
fi

echo "Checking requirements:"
ok=1
for c in python3 soffice pdfunite pdfseparate pdftotext pdfinfo fc-match; do
  if command -v "$c" >/dev/null; then echo "  ok   $c"; else echo "  MISSING $c"; ok=0; fi
done
for m in yaml PIL; do
  if python3 -c "import $m" 2>/dev/null; then echo "  ok   python: $m"; else echo "  MISSING python module: $m"; ok=0; fi
done
if command -v fc-match >/dev/null && ! fc-match "Liberation Sans" | grep -qi liberation; then
  echo "  WARN Liberation Sans font not found (documents will use a fallback font)"
fi
if command -v claude >/dev/null; then
  for s in osm-nic refconv; do
    if claude mcp get "$s" >/dev/null 2>&1; then echo "  ok   MCP server: $s"; else echo "  MISSING MCP server: $s (see README)"; ok=0; fi
  done
fi
[ "$ok" = 1 ] && echo "Done. Start Claude Code in $WS and run /planAHike." || echo "Install the missing items above (see README)."
