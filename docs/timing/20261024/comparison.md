# Extracted trial comparison

Vectors are slow / typical / fast. All periods remain 20 ns. Every candidate fails strict signoff.

| Trial | Setup WS (ns) | Hold WS (ns) | Strict gate |
| --- | --- | --- | --- |
| Control | -6.809803 / 2.992410 / 7.564806 | 0.666255 / 0.314691 / 0.122530 | FAIL |
| Electrical repair | -6.669463 / 2.863112 / 7.451491 | 0.673130 / 0.318593 / 0.124617 | FAIL |
| CTS size 8 | -7.193721 / 3.022539 / 7.664167 | 0.672129 / 0.318188 / 0.125933 | FAIL |
| CTS plus branch split | -6.776606 / 3.295254 / 7.787775 | 0.642020 / 0.302309 / 0.115210 | FAIL |
| Post-GRT timing | -6.485150 / 3.362455 / 7.744005 | 0.652879 / 0.281565 / 0.046658 | FAIL |
| Parallel read (reverted) | -9.486900 / 0.149287 / 5.727881 | 0.667339 / 0.323764 / 0.126508 | FAIL |

| Trial | Setup TNS (ns) | Setup endpoints | Slew violations |
| --- | --- | --- | --- |
| Control | -979.921111 / 0.000000 / 0.000000 | 616 / 0 / 0 | 55 / 4 / 0 |
| Electrical repair | -1166.127309 / 0.000000 / 0.000000 | 628 / 0 / 0 | 53 / 0 / 0 |
| CTS size 8 | -1130.830501 / 0.000000 / 0.000000 | 618 / 0 / 0 | 52 / 6 / 0 |
| CTS plus branch split | -1055.483069 / 0.000000 / 0.000000 | 625 / 0 / 0 | 30 / 4 / 0 |
| Post-GRT timing | -1179.156390 / 0.000000 / 0.000000 | 629 / 0 / 0 | 58 / 2 / 0 |
| Parallel read (reverted) | -4689.111070 / 0.000000 / 0.000000 | 927 / 0 / 0 | 86 / 16 / 0 |

| Trial | Cap violations | Fanout violations | Cell area (um2) | Utilization |
| --- | --- | --- | ---: | ---: |
| Control | 0 / 0 / 0 | 183 / 183 / 183 | 369414 | 0.305762 |
| Electrical repair | 0 / 0 / 0 | 178 / 178 / 178 | 369294 | 0.305663 |
| CTS size 8 | 1 / 1 / 1 | 9 / 9 / 9 | 375635 | 0.310912 |
| CTS plus branch split | 0 / 0 / 0 | 7 / 7 / 7 | 375748 | 0.311005 |
| Post-GRT timing | 0 / 0 / 0 | 183 / 183 / 183 | 369479 | 0.305816 |
| Parallel read (reverted) | 6 / 6 / 6 | 186 / 186 / 186 | 366710 | 0.303525 |

All hold TNS/violation counts and filtered annotation gaps are zero in all corners.
Remaining Magic checks were intentionally interrupted after timing rejection. DRC/LVS/precheck acceptance is not claimed.
Native optional r2r summary fields may contain Infinity; they are not used as passing evidence. Restricted STA reports provide numeric register-path results.
