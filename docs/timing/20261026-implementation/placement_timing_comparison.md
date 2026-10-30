# placement_timing versus placement_control

Vectors: slow / typical / fast. Delta = candidate minus control.

| Metric | Control | Candidate | Delta | Candidate |
| --- | --- | --- | --- | --- |
| Setup WS (ns) | -6.809803 / 2.992410 / 7.564806 | -4.019178 / 3.520288 / 7.896596 | 2.790625 / 0.527878 / 0.331790 | FAIL |
| Hold WS (ns) | 0.666255 / 0.314691 / 0.122530 | 0.672997 / 0.328550 / 0.129108 | 0.006742 / 0.013858 / 0.006579 | PASS |
| Setup TNS (ns) | -979.921111 / 0 / 0 | -360.433613 / 0 / 0 | 619.487498 / 0 / 0 | FAIL |
| Hold TNS (ns) | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | PASS |
| Setup endpoints | 616 / 0 / 0 | 435 / 0 / 0 | -181 / 0 / 0 | FAIL |
| Hold endpoints | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | PASS |
| Slew violations | 55 / 4 / 0 | 65 / 0 / 0 | 10 / -4 / 0 | FAIL |
| Cap violations | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | PASS |
| Fanout violations | 183 / 183 / 183 | 174 / 174 / 174 | -9 / -9 / -9 | FAIL |
| Filtered annotation gaps | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | PASS |
| Standard-cell area excluding filler (um2) | 369414 | 368697 | -717.000000 | INFO |
| Standard-cell utilization | 0.305762 | 0.305169 | -0.000593 | INFO |
| Inferred latches | 0 | 0 | 0.000000 | PASS |
| Unmapped cells | 0 | 0 | 0.000000 | PASS |
| Synthesis check errors | 0 | 0 | 0.000000 | PASS |

Strict gate: control FAIL; candidate FAIL.

This is extracted screening evidence. Full GDS/DRC/LVS/antenna/precheck and final gate-level verification remain required before acceptance.
