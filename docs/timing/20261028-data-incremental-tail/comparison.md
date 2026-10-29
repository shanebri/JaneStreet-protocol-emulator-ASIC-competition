# Native incremental-routing comparison

| Case | Corner | Setup ns | Hold ns | Slew | Fanout | Gaps |
| --- | --- | --- | --- | --- | --- | --- |
| control | nom_slow_1p08V_125C | 0.249125172 | 0.375747777 | 0 | 3 | 0 |
| control | nom_typ_1p20V_25C | 6.092250432 | 0.147292627 | 0 | 3 | 0 |
| control | nom_fast_1p32V_m40C | 9.495303479 | 0.013692159 | 0 | 3 | 0 |

control: unchanged serialized routes 13882/25358; changed clock routes 252; strict gate FAIL.

| last_fanout | nom_slow_1p08V_125C | 0.044533267 | 0.371877983 | 0 | 4 | 0 |
| last_fanout | nom_typ_1p20V_25C | 5.964107599 | 0.144944727 | 0 | 4 | 0 |
| last_fanout | nom_fast_1p32V_m40C | 9.395180011 | 0.012285284 | 0 | 4 | 0 |

last_fanout: unchanged serialized routes 13942/25358; changed clock routes 247; strict gate FAIL.

Complete metrics, setup/hold TNS and counts, coverage, model hashes and physical deltas are in comparison.json.
Native DRC/antenna, GDS qualification and functional verification remain distinct gates.
