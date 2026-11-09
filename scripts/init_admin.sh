#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python scripts/init_admin.py
