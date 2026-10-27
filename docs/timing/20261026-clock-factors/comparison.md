# Clock factor comparison

Matched 2x2 screens: automatic/size-8 clustering and no/maximum-8 branch splitting. All four still fail strict signoff.

| Trial | Slow WS ns | Slow TNS ns | Setup endpoints | Slow slew | Total fanout/corner | Clock outputs above 8 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [clock_control](clock_control-01/sta/metrics.json) | -0.981842 | -13.117230 | 19 | 30 | 172 | 166 |
| [clock_cluster8](clock_cluster8-01/sta/metrics.json) | -1.591101 | -22.324372 | 28 | 32 | 8 | 0 |
| [clock_split8](clock_split8-01/sta/metrics.json) | -1.184761 | -16.385711 | 23 | 28 | 6 | 0 |
| [clock_cap8](clock_cap8-01/sta/metrics.json) | -1.591101 | -22.324372 | 28 | 32 | 8 | 0 |

Splitting-only is the preferred clock-fanout repair candidate: 0.202919 ns setup penalty versus control, compared with 0.609258 ns for clustering. It recovers 0.406340 ns versus the combined recipe. Six non-clock fanout violations remain.

Clustering-only and combined post-CTS ODBs are byte-identical; combined inserts zero branch buffers. Their extracted results reproduce exactly.

All four retain complete annotation, positive all-corner hold, zero capacitance violations and zero final native routing DRC/antenna violations. All 36 STA replay sessions complete without constraint coverage issues. Clock-latency spread worsens, so this remains an experimental tradeoff.
