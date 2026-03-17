#!/usr/bin/env bash
set -euo pipefail

# One-command stage-5 run with sensible defaults.
#
# Usage:
#   ./run_stage5_resplit.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/pdfs/run_stage5_resplit_all.sh"

