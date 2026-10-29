#!/usr/bin/env bash
set -euo pipefail
repo=/mnt/c/Users/shane/Projects/JaneStreet-protocol-emulator-ASIC-competition
cd /home/shane/eda/librelane-3.1.0.dev3
nohup setsid env PYTHONDONTWRITEBYTECODE=1 /nix/var/nix/profiles/default/bin/nix develop --offline --command python3 "$repo/tools/timing/data_eco_suite.py" \
  --suite critical_path --base "$repo/test/sim_build/clock_factors/clock_split8-01" \
  --prepared "$repo/test/sim_build/data_eco_20261027/input" \
  --archive-root /home/shane/eda/timing-20261024/current --pdk-root /home/shane/eda/pdk-2bbec755 \
  --root "$repo/test/sim_build/data_critical_path_20261027" \
  --evidence "$repo/docs/timing/20261027-data-critical-path" --jobs 3 \
  > "$repo/test/sim_build/data_critical_path_20261027/scheduler.log" 2>&1 < /dev/null &
printf '%s\n' "$!" > "$repo/test/sim_build/data_critical_path_20261027/scheduler.pid"
