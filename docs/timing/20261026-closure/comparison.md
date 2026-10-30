# Controlled closure experiment comparison

All rows fail the unchanged strict signoff gate. Compare candidates only with their named matched control. Full qualification remains required.

| Trial | Slow WS ns | Slow TNS ns | Setup endpoints | Slow slew | Fanout/corner | Cap max | Filtered gaps max | Hold min ns |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [grt_capacity25-01](grt_capacity25-01/metrics.json) | -0.981842 | -13.117230 | 19 | 30 | 172 | 0 | 0 | 0.124546 |
| [clock_control-01](clock_control-01/metrics.json) | -0.981842 | -13.117230 | 19 | 30 | 172 | 0 | 0 | 0.124546 |
| [clock_cap8-01](clock_cap8-01/metrics.json) | -1.591101 | -22.324372 | 28 | 32 | 8 | 0 | 0 | 0.122341 |
| [driver_control-01](driver_control-01/metrics.json) | -0.981842 | -13.117230 | 19 | 30 | 172 | 0 | 0 | 0.124546 |
| [driver_nor3-01](driver_nor3-01/metrics.json) | -1.032022 | -13.538630 | 19 | 25 | 173 | 0 | 0 | 0.122561 |
| [host_control-01](host_control-01/metrics.json) | -0.955799 | -7.096958 | 21 | 17 | 179 | 0 | 0 | 0.121943 |
| [host_pending_word-01](host_pending_word-01/metrics.json) | -2.529188 | -152.623504 | 270 | 9 | 181 | 2 | 0 | 0.119787 |

Decisions: retain GRT 0.25 as a coverage-clean experimental baseline. Clock cap8 is an electrical option with a setup penalty. Reject NOR3 sizing and host pending-class caching as global timing regressions. The host RTL patch is archived and reverted.

All seven screens have complete nine-session replay matrices and no constraint coverage issues. GDS LVS proofs are in diagnosis/. Production RTL is byte-identical to the frozen pre-experiment baseline.
