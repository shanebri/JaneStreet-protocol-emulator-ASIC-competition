# Terminal NOR: extracted A/B comparison

Vectors: slow / typical / fast. Changes are candidate minus control; positive WS change is an improvement.

| Metric | Matched control | Sized NOR | Change | Candidate |
| --- | --- | --- | --- | --- |
| Setup WS (ns) | -6.809803 / 2.992410 / 7.564806 | -5.992693 / 3.234703 / 7.670321 | 0.817110 / 0.242293 / 0.105516 | FAIL |
| Hold WS (ns) | 0.666255 / 0.314691 / 0.122530 | 0.669025 / 0.313078 / 0.117578 | 0.002770 / -0.001613 / -0.004952 | PASS |
| Setup TNS (ns) | -979.921111 / 0 / 0 | -1006.726990 / 0 / 0 | -26.805879 / 0 / 0 | FAIL |
| Hold TNS (ns) | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | PASS |
| Setup endpoints | 616 / 0 / 0 | 632 / 0 / 0 | 16 / 0 / 0 | FAIL |
| Hold endpoints | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | PASS |
| Slew violations | 55 / 4 / 0 | 59 / 6 / 0 | 4 / 2 / 0 | FAIL |
| Cap violations | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | PASS |
| Fanout violations | 183 / 183 / 183 | 178 / 178 / 178 | -5 / -5 / -5 | FAIL |
| Unannotated filtered nets | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | PASS |
| Standard-cell area excluding filler (um2) | 369414 | 369365 | -49 | INFO |
| Standard-cell utilization | 0.305762 | 0.305722 | -3.999999999998449e-05 | INFO |
| Inferred latches | 0 | 0 | 0 | PASS |
| Unmapped cells | 0 | 0 | 0 | PASS |
| Synthesis check errors | 0 | 0 | 0 | PASS |
| RTL/standalone/differential/FPGA regression | PASS | PASS (shared RTL) | — | PASS |
| Final gate-level/GDS/DRC/LVS/precheck | Incomplete | Incomplete | — | NOT QUALIFIED |

Strict gate: control FAIL; candidate FAIL. DRC/LVS/GDS/precheck/final gate-level qualification are not completed by these screening runs.
