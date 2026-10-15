#!/usr/bin/env bash
# Post-deployment smoke test with measured numbers.
# Waits for the load balancer, verifies the storefront and the live RDS connection (TLS), samples
# latency and records which Availability Zones / instances actually served traffic.
#
# Usage: scripts/smoke-test.sh <alb-dns-name-or-url>
# Env:   SMOKE_TIMEOUT_SECONDS (default 900), SMOKE_SAMPLES (default 40)
# Requires: curl, jq
set -euo pipefail

TARGET=${1:?usage: smoke-test.sh <alb-dns-name-or-url>}
TIMEOUT=${SMOKE_TIMEOUT_SECONDS:-900}
SAMPLES=${SMOKE_SAMPLES:-40}
case "$TARGET" in http://*|https://*) BASE=${TARGET%/} ;; *) BASE="http://${TARGET%/}" ;; esac

fail() { echo "::error title=Smoke test failed::$*"; exit 1; }
deadline=$((SECONDS + TIMEOUT))

echo "Waiting for $BASE/health (up to ${TIMEOUT}s)"
until curl -fsSL --max-time 5 "$BASE/health" >/dev/null 2>&1; do
  [ "$SECONDS" -lt "$deadline" ] || fail "$BASE/health never returned 200"
  sleep 10
done
echo "Health OK after ${SECONDS}s"

echo "Waiting for a live database connection"
status=""
until status=$(curl -fsSL --max-time 10 "$BASE/api/status" 2>/dev/null) \
  && jq -e '.database.connected == true' >/dev/null <<<"$status"; do
  [ "$SECONDS" -lt "$deadline" ] || fail "database not connected: ${status:-no response}"
  sleep 10
done
jq -e '.database.tls == true' >/dev/null <<<"$status" || fail "database connection is not encrypted"

curl -fsSL --max-time 10 "$BASE/" | grep -q "Nimbus" || fail "storefront did not render"
curl -fsSL --max-time 10 "$BASE/api/products" | jq -e '.count >= 1' >/dev/null || fail "catalog is empty"
curl -fsSIL --max-time 10 "$BASE/" | grep -qi '^content-security-policy:' || fail "security headers missing"

declare -a times=()
declare -A zones=() instances=()
for _ in $(seq 1 "$SAMPLES"); do
  t=$(curl -sSL -o /dev/null -w '%{time_total}' --max-time 10 "$BASE/")
  times+=("$(awk -v t="$t" 'BEGIN { printf "%.1f", t * 1000 }')")
  s=$(curl -fsSL --max-time 10 "$BASE/api/status" || true)
  az=$(jq -r '.application.az // "unknown"' <<<"$s" 2>/dev/null || echo unknown)
  id=$(jq -r '.application.instance_id // "unknown"' <<<"$s" 2>/dev/null || echo unknown)
  zones[$az]=1
  instances[$id]=1
done

sorted=$(printf '%s\n' "${times[@]}" | sort -n)
pick() { sed -n "${1}p" <<<"$sorted"; }
n=${#times[@]}
p50=$(pick $(( (n + 1) / 2 )))
p95=$(pick $(( (n * 95 + 99) / 100 )))
max=$(pick "$n")
waf=$(curl -sSL -o /dev/null -w '%{http_code}' --max-time 10 -G --data-urlencode 'q=<script>alert(1)</script>' "$BASE/" || echo n/a)

summary=$(cat <<MD
### Smoke test results
| Metric | Value |
|---|---|
| Time to healthy | ${SECONDS}s |
| Database | $(jq -r '"\(.database.engine) \(.database.version), TLS \(.database.cipher), \(.database.latency_ms) ms query"' <<<"$status") |
| Catalog rows | $(jq -r '.database.products' <<<"$status") |
| Samples | $n requests to \`/\` |
| Latency p50 / p95 / max | ${p50} / ${p95} / ${max} ms |
| Availability Zones that served traffic | ${#zones[@]} (${!zones[*]}) |
| Instances that served traffic | ${#instances[@]} |
| WAF response to XSS probe | HTTP ${waf} |
MD
)
echo "$summary"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then echo "$summary" >> "$GITHUB_STEP_SUMMARY"; fi
echo "Smoke test passed"
