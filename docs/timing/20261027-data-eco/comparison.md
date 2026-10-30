# Isolated data ECO comparison

Compare each row with the matched full-reroute control. The older splitting-only routed reference has a different routing history. All rows fail strict signoff. Positive WS delta means improvement.

| Trial | WS ns | WS delta ns | TNS ns | Endpoints | Slew | Fanout/corner | Complete annotation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| [control](control-01/sta/metrics.json) | -0.971601 | 0.000000 | -13.406668 | 22 | 62 | 12 | yes |
| [critical_size](critical_size-01/sta/metrics.json) | -1.151809 | -0.180208 | -16.413563 | 24 | 60 | 10 | yes |
| [critical_buffer](critical_buffer-01/sta/metrics.json) | -0.857634 | +0.113968 | -9.450856 | 20 | 51 | 11 | yes |
| [fanout_uio3](fanout_uio3-02/sta/metrics.json) | -1.312884 | -0.341283 | -16.795502 | 28 | 52 | 7 | NO: reject raw timing |
| [fanout_uio2](fanout_uio2-02/sta/metrics.json) | -0.979190 | -0.007589 | -11.336264 | 23 | 33 | 12 | yes |
| [fanout_17026](fanout_17026-02/sta/metrics.json) | -1.165377 | -0.193776 | -16.679094 | 26 | 42 | 10 | NO: reject raw timing |
| [fanout_16949](fanout_16949-02/sta/metrics.json) | -0.960558 | +0.011044 | -12.279937 | 21 | 37 | 10 | yes |
| [fanout_32068](fanout_32068-02/sta/metrics.json) | -1.802262 | -0.830660 | -28.808027 | 42 | 38 | 7 | yes |
| [fanout_32071](fanout_32071-02/sta/metrics.json) | -0.962006 | +0.009596 | -9.198402 | 20 | 46 | 9 | yes |
| [slew_19177](slew_19177-01/sta/metrics.json) | -1.183722 | -0.212120 | -14.287270 | 23 | 29 | 10 | yes |
| [slew_24358](slew_24358-01/sta/metrics.json) | -1.440482 | -0.468880 | -23.454876 | 41 | 34 | 9 | yes |
| [slew_28038](slew_28038-02/sta/metrics.json) | -1.084150 | -0.112548 | -16.142158 | 24 | 58 | 11 | yes |
| [slew_29030](slew_29030-02/sta/metrics.json) | -0.915861 | +0.055740 | -11.916253 | 26 | 16 | 9 | yes |
| [slew_18133](slew_18133-02/sta/metrics.json) | -1.400471 | -0.428869 | -21.734467 | 31 | 47 | 13 | NO: reject raw timing |
| [slew_23931](slew_23931-02/sta/metrics.json) | -1.092097 | -0.120496 | -16.088571 | 24 | 59 | 9 | yes |

The original endpoint improves from -0.971601 ns to +0.417908 ns with the critical output buffer; global WS improves to -0.857634 ns as the worst endpoint moves.

Useful individual candidates: critical_buffer, fanout_16949, fanout_32071; slew_29030 gives the strongest slew reduction but adds setup endpoints. Their effects are not assumed additive.

Three incomplete-annotation cases are rejected. All fifteen have passing logical ECO audits, nine STA replay sessions each, zero native final routing DRC/antenna violations, zero cap violations, positive hold and zero overloaded clock-buffer outputs. Architecture/production RTL and acceptance gates remain unchanged.
