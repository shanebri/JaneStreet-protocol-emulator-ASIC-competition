# placement_corners versus placement_timing

Vectors: slow / typical / fast. Delta = candidate minus control.

| Metric | Control | Candidate | Delta | Candidate |
| --- | --- | --- | --- | --- |
| Setup WS (ns) | -4.019178 / 3.520288 / 7.896596 | -1.440862 / 5.122854 / 8.910012 | 2.578316 / 1.602566 / 1.013416 | FAIL |
| Hold WS (ns) | 0.672997 / 0.328550 / 0.129108 | 0.656217 / 0.322299 / 0.127587 | -0.016780 / -0.006251 / -0.001522 | PASS |
| Setup TNS (ns) | -360.433613 / 0 / 0 | -22.343168 / 0 / 0 | 338.090445 / 0 / 0 | FAIL |
| Hold TNS (ns) | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | PASS |
| Setup endpoints | 435 / 0 / 0 | 33 / 0 / 0 | -402 / 0 / 0 | FAIL |
| Hold endpoints | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | PASS |
| Slew violations | 65 / 0 / 0 | 27 / 0 / 0 | -38 / 0 / 0 | FAIL |
| Cap violations | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | PASS |
| Fanout violations | 174 / 174 / 174 | 178 / 178 / 178 | 4 / 4 / 4 | FAIL |
| Filtered annotation gaps | 0 / 0 / 0 | 1 / 1 / 1 | 1 / 1 / 1 | FAIL |
| Standard-cell area excluding filler (um2) | 368697 | 369537 | 840.000000 | INFO |
| Standard-cell utilization | 0.305169 | 0.305864 | 0.000695 | INFO |
| Inferred latches | 0 | 0 | 0.000000 | PASS |
| Unmapped cells | 0 | 0 | 0.000000 | PASS |
| Synthesis check errors | 0 | 0 | 0.000000 | PASS |

Strict gate: control FAIL; candidate FAIL.

This is extracted screening evidence. Full GDS/DRC/LVS/antenna/precheck and final gate-level verification remain required before acceptance.
