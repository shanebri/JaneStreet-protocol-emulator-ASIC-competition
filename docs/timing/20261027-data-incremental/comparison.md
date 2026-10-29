# Native incremental-routing comparison

| Case | Corner | Setup ns | Hold ns | Slew | Fanout | Gaps |
| --- | --- | --- | --- | --- | --- | --- |
| control | nom_slow_1p08V_125C | -0.016591173 | 0.373025510 | 0 | 6 | 0 |
| control | nom_typ_1p20V_25C | 5.913645740 | 0.145813366 | 0 | 6 | 0 |
| control | nom_fast_1p32V_m40C | 9.375943842 | 0.012809421 | 0 | 6 | 0 |

control: unchanged serialized routes 3034/25346; changed clock routes 512; strict gate FAIL.

| fanout | nom_slow_1p08V_125C | 0.305021794 | 0.373383779 | 0 | 1 | 0 |
| fanout | nom_typ_1p20V_25C | 6.122039049 | 0.145897187 | 0 | 1 | 0 |
| fanout | nom_fast_1p32V_m40C | 9.517193525 | 0.012887691 | 0 | 1 | 0 |

fanout: unchanged serialized routes 2940/25346; changed clock routes 511; strict gate FAIL.

Complete metrics, setup/hold TNS and counts, coverage, model hashes and physical deltas are in comparison.json.
Native DRC/antenna, GDS qualification and functional verification remain distinct gates.
