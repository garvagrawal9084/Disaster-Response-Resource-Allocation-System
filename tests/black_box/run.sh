#!/usr/bin/env bash
set -euo pipefail

test_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$test_dir/../.."

export FRONTEND_PORT="${DRRAS_TEST_FRONTEND_PORT:-18080}"
export API_PORT="${DRRAS_TEST_API_PORT:-18000}"
export OSRM_URL=http://127.0.0.1:1
export FALLBACK_SPEED_KMH=30
export UNMET_PENALTY_SECONDS=7200
export DRRAS_TEST_URL="http://127.0.0.1:$FRONTEND_PORT"
export DRRAS_TEST_RESULTS
DRRAS_TEST_RESULTS="$(mktemp -d "${TMPDIR:-/tmp}/drras-black-box.XXXXXXXX")"
project="drras-black-box-$(date +%s)-$$"

compose() {
  docker compose -p "$project" "$@"
}

cleanup() {
  compose down --volumes
}
trap cleanup EXIT

printf 'Test results directory: %s\n' "$DRRAS_TEST_RESULTS"
compose up --build --wait --wait-timeout 100 -d

status=0
node "$test_dir/browser_checks.cjs" || status=1
python3 -E "$test_dir/api_checks.py" || status=1

compose restart database backend || status=1
for attempt in {1..30}; do
  if curl -fsS --max-time 2 "$DRRAS_TEST_URL/api/health" > "$DRRAS_TEST_RESULTS/restart_health.json" 2>/dev/null; then
    break
  fi
  sleep 1
done
python3 -E "$test_dir/api_checks.py" after-restart || status=1

printf 'Test results directory: %s\n' "$DRRAS_TEST_RESULTS"
exit "$status"
