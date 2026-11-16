#!/bin/sh
# Start an MCP server with API keys loaded from your private workspace .env.
#   with-env.sh ENV_FILE COMMAND [ARGS...]
# Keys stay in one file outside every git repo; register servers like:
#   claude mcp add -s user refconv -- <workspace>/hike-kit/bin/with-env.sh <workspace>/.env /path/to/RefConvMCP/run.sh
ENV_FILE=$1; shift
if [ ! -f "$ENV_FILE" ]; then echo "with-env.sh: $ENV_FILE not found" >&2; exit 1; fi
set -a; . "$ENV_FILE"; set +a
exec "$@"
