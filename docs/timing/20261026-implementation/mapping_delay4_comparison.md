# mapping_delay4 versus mapping_control

Vectors: slow / typical / fast. Delta = candidate minus control.

| Metric | Control | Candidate | Delta | Candidate |
| --- | --- | --- | --- | --- |
| Setup WS (ns) | -6.809803 / 2.992410 / 7.564806 | -1.825343 / 4.644223 / 7.404213 | 4.984459 / 1.651813 / -0.160593 | FAIL |
| Hold WS (ns) | 0.666255 / 0.314691 / 0.122530 | 0.671722 / 0.320232 / 0.117383 | 0.005467 / 0.005540 / -0.005147 | PASS |
| Setup TNS (ns) | -979.921111 / 0 / 0 | -32.948461 / 0 / 0 | 946.972650 / 0 / 0 | FAIL |
| Hold TNS (ns) | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | PASS |
| Setup endpoints | 616 / 0 / 0 | 39 / 0 / 0 | -577 / 0 / 0 | FAIL |
| Hold endpoints | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | PASS |
| Slew violations | 55 / 4 / 0 | 141 / 25 / 0 | 86 / 21 / 0 | FAIL |
| Cap violations | 0 / 0 / 0 | 19 / 20 / 20 | 19 / 20 / 20 | FAIL |
| Fanout violations | 183 / 183 / 183 | 187 / 187 / 187 | 4 / 4 / 4 | FAIL |
| Filtered annotation gaps | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | PASS |
| Standard-cell area excluding filler (um2) | 369414 | 377158 | 7744.000000 | INFO |
| Standard-cell utilization | 0.305762 | 0.312172 | 0.006410 | INFO |
| Inferred latches | 0 | 0 | 0.000000 | PASS |
| Unmapped cells | 0 | 0 | 0.000000 | PASS |
| Synthesis check errors | 0 | 0 | 0.000000 | PASS |

Strict gate: control FAIL; candidate FAIL.

This is extracted screening evidence. Full GDS/DRC/LVS/antenna/precheck and final gate-level verification remain required before acceptance.
