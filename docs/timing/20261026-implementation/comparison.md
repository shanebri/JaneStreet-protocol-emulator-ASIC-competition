# Extracted implementation experiment overview

All screens use 20 ns and the original 8x4 allocation. No candidate is accepted solely from this table.

| Trial | Slow setup WS (ns) | Slow TNS (ns) | Setup endpoints | Slow slew | Fanout/corner | Gaps/corner | Strict gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| placement-control-01 | -6.809803 | -979.921111 | 616 | 55 | 183 | 0 | FAIL |
| placement-timing-01 | -4.019178 | -360.433613 | 435 | 65 | 174 | 0 | FAIL |
| placement-corners-01 | -1.440862 | -22.343168 | 33 | 27 | 178 | 1 | FAIL |
| mapping-control-01 | -6.809803 | -979.921111 | 616 | 55 | 183 | 0 | FAIL |
| mapping-delay4-01 | -1.825343 | -32.948461 | 39 | 141 | 187 | 0 | FAIL |

45 independent STA diagnostic sessions completed. Per-pair reports:

- [Timing-driven placement](placement_timing_comparison.md)
- [Placement corner selection](placement_corners_comparison.md)
- [Independent delay-oriented mapping](mapping_delay4_comparison.md)

Zero reported constraint-coverage issues do not excuse parasitic annotation gaps. The three-view placement screen has one live input net with partially disconnected SPEF resistance branches; its raw filter output, net excerpt and graph diagnostic are preserved.

Full GDS/Magic DRC/LVS/antenna/precheck/final gate-level qualification is incomplete for these screens.
