# Integration data ECO comparison

All cases start from the same prepared input and use a matched full reroute. Positive slack deltas mean improvement. Screen validity does not imply strict signoff.

| Case | WS ns | Delta control | Delta previous | TNS ns | Endpoints | Slew | Fanout | Annotation | Valid screen |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| [1](control-01/sta/metrics.json) | -0.971601 | +0.000000 | +0.000000 | -13.406668 | 22 | 62 | 12 | complete | yes |
| [2](critical_buffer-01/sta/metrics.json) | -0.857634 | +0.113968 | +0.113968 | -9.450856 | 20 | 51 | 11 | complete | yes |
| [3](critical_buffer_fanout_32071-01/sta/metrics.json) | -0.680044 | +0.291557 | +0.177590 | -6.082395 | 17 | 44 | 13 | complete | yes |
| [4](critical_buffer_fanout_32071_16949-01/sta/metrics.json) | -1.077670 | -0.106068 | -0.397625 | -16.392298 | 31 | 41 | 8 | complete | yes |
| [5](critical_buffer_fanout_32071_16949_slew_29030-01/sta/metrics.json) | -1.032133 | -0.060531 | +0.045537 | -12.700797 | 29 | 35 | 10 | REJECT | NO |

1. `control`: `ui_in[1] (input port clocked by clk)` to `_33836_ (rising edge-triggered flip-flop clocked by clk)`. Strict signoff: FAIL.
2. `critical_buffer`: `ui_in[2] (input port clocked by clk)` to `_31995_ (rising edge-triggered flip-flop clocked by clk)`. Strict signoff: FAIL.
3. `critical_buffer_fanout_32071`: `ui_in[1] (input port clocked by clk)` to `_31996_ (rising edge-triggered flip-flop clocked by clk)`. Strict signoff: FAIL.
4. `critical_buffer_fanout_32071_16949`: `ui_in[1] (input port clocked by clk)` to `_31996_ (rising edge-triggered flip-flop clocked by clk)`. Strict signoff: FAIL.
5. `critical_buffer_fanout_32071_16949_slew_29030`: `ui_in[1] (input port clocked by clk)` to `_31996_ (rising edge-triggered flip-flop clocked by clk)`. Strict signoff: FAIL.

Best valid combination by global setup WS: `critical_buffer_fanout_32071`.

Old routed reference: WS -1.184761 ns, TNS -16.385711 ns, 23 endpoints, 28 slew and 6 fanout violations. Per-case deltas against this different routing history are retained in comparison.json.
