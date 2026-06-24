#!/usr/bin/env bash
# qatp_live.sh — Live QA test plan for TailoredLoop production
# Usage: ./scripts/qatp_live.sh [BASE_URL]
# Default BASE_URL: https://shopassistant.verbboard.com

set -euo pipefail

BASE="${1:-https://shopassistant.verbboard.com}"
FAIL=0

pass() { printf "PASS  %s\n" "$1"; }
fail() { printf "FAIL  %s\n  -> %s\n" "$1" "$2"; FAIL=1; }

# ---------------------------------------------------------------------------
# 1. Criteria bar — GET /<search_name> HTML must contain criteria-bar div
# ---------------------------------------------------------------------------
BODY=$(curl -sf --max-time 15 "${BASE}/wax_coat" 2>&1) || { fail "1 criteria-bar HTML fetch" "curl error: $BODY"; BODY=""; }
if [ -n "$BODY" ]; then
  echo "$BODY" | grep -q 'id="criteria-bar"' \
    && pass "1 criteria-bar div present in /wax_coat HTML" \
    || fail "1 criteria-bar div present in /wax_coat HTML" "id=\"criteria-bar\" not found in page"
fi

# ---------------------------------------------------------------------------
# 2. Sidebar collapse button — GET / HTML must have sidebar-toggle-btn inside
#    .sidebar-header
# ---------------------------------------------------------------------------
ROOT=$(curl -sf --max-time 15 "${BASE}/" 2>&1) || { fail "2 sidebar-toggle-btn HTML fetch" "curl error: $ROOT"; ROOT=""; }
if [ -n "$ROOT" ]; then
  echo "$ROOT" | grep -q 'id="sidebar-toggle-btn"' \
    && pass "2 sidebar-toggle-btn present in / HTML" \
    || fail "2 sidebar-toggle-btn present in / HTML" "id=\"sidebar-toggle-btn\" not found"
  echo "$ROOT" | grep -q 'sidebar-header' \
    && pass "2 sidebar-header wrapper present in / HTML" \
    || fail "2 sidebar-header wrapper present in / HTML" "class=\"sidebar-header\" not found"
fi

# ---------------------------------------------------------------------------
# 3a. Config panel collapse — GET / HTML links admin.css
# ---------------------------------------------------------------------------
if [ -n "$ROOT" ]; then
  echo "$ROOT" | grep -q 'admin\.css' \
    && pass "3a admin.css <link> present in / HTML" \
    || fail "3a admin.css <link> present in / HTML" "admin.css link not found"
fi

# 3b. admin.css contains collapse classes
ADMINCSS=$(curl -sf --max-time 15 "${BASE}/static/admin.css" 2>&1) || { fail "3b admin.css fetch" "curl error: $ADMINCSS"; ADMINCSS=""; }
if [ -n "$ADMINCSS" ]; then
  echo "$ADMINCSS" | grep -q 'admin-panels--config-collapsed' \
    && pass "3b admin.css has .admin-panels--config-collapsed" \
    || fail "3b admin.css has .admin-panels--config-collapsed" "class not found"
  echo "$ADMINCSS" | grep -q 'panel-collapse-btn' \
    && pass "3b admin.css has .panel-collapse-btn" \
    || fail "3b admin.css has .panel-collapse-btn" "class not found"
fi

# 3c. admin.js contains config-collapse-btn
ADMINJS=$(curl -sf --max-time 15 "${BASE}/static/admin.js" 2>&1) || { fail "3c admin.js fetch" "curl error: $ADMINJS"; ADMINJS=""; }
if [ -n "$ADMINJS" ]; then
  echo "$ADMINJS" | grep -q 'config-collapse-btn' \
    && pass "3c admin.js contains config-collapse-btn" \
    || fail "3c admin.js contains config-collapse-btn" "identifier not found"
fi

# ---------------------------------------------------------------------------
# 4. Remove buttons — admin.js has btn-field-remove; admin.css must NOT have
#    the opacity:0.4 invisibility bug
# ---------------------------------------------------------------------------
if [ -n "$ADMINJS" ]; then
  echo "$ADMINJS" | grep -q 'btn-field-remove' \
    && pass "4 admin.js has btn-field-remove" \
    || fail "4 admin.js has btn-field-remove" "identifier not found"
fi
if [ -n "$ADMINCSS" ]; then
  echo "$ADMINCSS" | grep -v 'btn-field-remove' | grep -q 'opacity: 0\.4' \
    && fail "4 admin.css opacity:0.4 bug (remove buttons invisible)" "opacity: 0.4 found outside btn-field-remove context" \
    || pass "4 admin.css no opacity:0.4 invisibility bug"
fi

# ---------------------------------------------------------------------------
# 5. OAuth routes
#    GET /auth/login  => 503 (not configured) OR 302/301 to Google
#    POST /auth/logout => 200 {"ok":true}
# ---------------------------------------------------------------------------
LOGIN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "${BASE}/auth/login")
if [ "$LOGIN_STATUS" = "503" ] || [ "$LOGIN_STATUS" = "302" ] || [ "$LOGIN_STATUS" = "301" ]; then
  pass "5 GET /auth/login returns $LOGIN_STATUS (503 or Google redirect)"
else
  fail "5 GET /auth/login returns $LOGIN_STATUS (503 or Google redirect)" "got HTTP $LOGIN_STATUS"
fi

LOGOUT_BODY=$(curl -sf -X POST --max-time 15 "${BASE}/auth/logout" 2>&1) || { fail "5 POST /auth/logout" "curl error"; LOGOUT_BODY=""; }
if [ -n "$LOGOUT_BODY" ]; then
  echo "$LOGOUT_BODY" | grep -q '"ok":true' \
    && pass "5 POST /auth/logout returns {\"ok\":true}" \
    || fail "5 POST /auth/logout returns {\"ok\":true}" "got: $LOGOUT_BODY"
fi

# ---------------------------------------------------------------------------
# 6. GET /api/me anonymous => {"role":"free","anonymous":true}
# ---------------------------------------------------------------------------
ME=$(curl -sf --max-time 15 "${BASE}/api/me" 2>&1) || { fail "6 GET /api/me" "curl error: $ME"; ME=""; }
if [ -n "$ME" ]; then
  echo "$ME" | grep -q '"role":"free"' \
    && pass "6 GET /api/me anonymous has role:free" \
    || fail "6 GET /api/me anonymous has role:free" "got: $ME"
  echo "$ME" | grep -q '"anonymous":true' \
    && pass "6 GET /api/me anonymous has anonymous:true" \
    || fail "6 GET /api/me anonymous has anonymous:true" "got: $ME"
fi

# ---------------------------------------------------------------------------
# 7. GET /api/searches => JSON array; every item has name, active, visibility
# ---------------------------------------------------------------------------
SEARCHES=$(curl -sf --max-time 15 "${BASE}/api/searches" 2>&1) || { fail "7 GET /api/searches" "curl error: $SEARCHES"; SEARCHES=""; }
if [ -n "$SEARCHES" ]; then
  # Must be a JSON array (starts with "[")
  echo "$SEARCHES" | grep -q '^\[' \
    && pass "7 GET /api/searches returns a JSON array" \
    || fail "7 GET /api/searches returns a JSON array" "got: ${SEARCHES:0:120}"
  # Every returned object must have all three keys
  if command -v jq >/dev/null 2>&1; then
    MISSING=$(echo "$SEARCHES" | jq '[.[] | select(has("name") and has("active") and has("visibility") | not)] | length')
    [ "$MISSING" = "0" ] \
      && pass "7 /api/searches all items have name, active, visibility" \
      || fail "7 /api/searches all items have name, active, visibility" "$MISSING item(s) missing a key"
  else
    # Fallback without jq — just check keys appear somewhere in the payload
    echo "$SEARCHES" | grep -q '"name"' && echo "$SEARCHES" | grep -q '"active"' && echo "$SEARCHES" | grep -q '"visibility"' \
      && pass "7 /api/searches payload contains name, active, visibility keys" \
      || fail "7 /api/searches payload contains name, active, visibility keys" "one or more keys absent"
  fi
fi

# ---------------------------------------------------------------------------
# 8. GET /api/search/wax_coat => JSON with search_name, criteria, preferred_shops
# ---------------------------------------------------------------------------
WAXCOAT=$(curl -sf --max-time 15 "${BASE}/api/search/wax_coat" 2>&1) || { fail "8 GET /api/search/wax_coat" "curl error: $WAXCOAT"; WAXCOAT=""; }
if [ -n "$WAXCOAT" ]; then
  echo "$WAXCOAT" | grep -q '"search_name"' \
    && pass "8 /api/search/wax_coat has search_name" \
    || fail "8 /api/search/wax_coat has search_name" "got: ${WAXCOAT:0:120}"
  echo "$WAXCOAT" | grep -q '"criteria"' \
    && pass "8 /api/search/wax_coat has criteria" \
    || fail "8 /api/search/wax_coat has criteria" "got: ${WAXCOAT:0:120}"
  echo "$WAXCOAT" | grep -q '"preferred_shops"' \
    && pass "8 /api/search/wax_coat has preferred_shops" \
    || fail "8 /api/search/wax_coat has preferred_shops" "got: ${WAXCOAT:0:120}"
fi

# ---------------------------------------------------------------------------
# 9. /privacy and /terms — 200 HTML containing "TailoredLoop"
# ---------------------------------------------------------------------------
for PAGE in /privacy /terms; do
  PHTML=$(curl -sf --max-time 15 "${BASE}${PAGE}" 2>&1) || { fail "9 GET ${PAGE} fetch" "curl error: $PHTML"; PHTML=""; }
  if [ -n "$PHTML" ]; then
    echo "$PHTML" | grep -qi 'TailoredLoop' \
      && pass "9 GET ${PAGE} returns 200 HTML with TailoredLoop" \
      || fail "9 GET ${PAGE} returns 200 HTML with TailoredLoop" "brand string absent"
  fi
done

# ---------------------------------------------------------------------------
# 10. Static assets — app.js and app.css return 200
# ---------------------------------------------------------------------------
for ASSET in /static/app.js /static/app.css; do
  ASSET_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "${BASE}${ASSET}")
  [ "$ASSET_STATUS" = "200" ] \
    && pass "10 GET ${ASSET} returns 200" \
    || fail "10 GET ${ASSET} returns 200" "got HTTP $ASSET_STATUS"
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "All checks passed."
else
  echo "One or more checks FAILED."
  exit 1
fi
