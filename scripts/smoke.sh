#!/bin/sh
set -eu
base="${API_BASE:-http://127.0.0.1:8000}"
curl -fsS "$base/healthz"
echo
code="$(curl -sS -o /tmp/forge-ready.json -w "%{http_code}" "$base/readyz")"
cat /tmp/forge-ready.json
echo
if [ "$code" != "200" ] && [ "$code" != "503" ]; then
  echo "readyz 返回了意外状态码 $code" >&2
  exit 1
fi
