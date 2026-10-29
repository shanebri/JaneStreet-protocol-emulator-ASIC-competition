# Native incremental-routing comparison

| Case | Corner | Setup ns | Hold ns | Slew | Fanout | Gaps |
| --- | --- | --- | --- | --- | --- | --- |
| control | nom_slow_1p08V_125C | 0.304442702 | 0.373383557 | 0 | 1 | 0 |
| control | nom_typ_1p20V_25C | 6.121685554 | 0.145897076 | 0 | 1 | 0 |
| control | nom_fast_1p32V_m40C | 9.516919078 | 0.012887691 | 0 | 1 | 0 |

control: unchanged serialized routes 25339/25358; changed clock routes 0; strict gate FAIL.

| last_fanout | nom_slow_1p08V_125C | 0.303870715 | 0.373119990 | 0 | 0 | 0 |
| last_fanout | nom_typ_1p20V_25C | 6.121286762 | 0.145750416 | 0 | 0 | 0 |
| last_fanout | nom_fast_1p32V_m40C | 9.516648183 | 0.012811419 | 0 | 0 | 0 |

last_fanout: unchanged serialized routes 25327/25358; changed clock routes 1; strict gate PASS.

Complete metrics, setup/hold TNS and counts, coverage, model hashes and physical deltas are in comparison.json.
Native DRC/antenna, GDS qualification and functional verification remain distinct gates.
