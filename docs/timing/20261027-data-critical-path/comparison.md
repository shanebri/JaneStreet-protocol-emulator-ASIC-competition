# Critical_path data ECO comparison

All cases start from the same prepared input and use a matched full reroute. Positive slack deltas mean improvement. Screen validity does not imply strict signoff.

| Case | WS ns | Delta control | TNS ns | Endpoints | Slew | Fanout | Fast hold ns | Delta fast hold ns | Annotation | Valid screen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [1](critical_buffer_fanout_32071-01/sta/metrics.json) | -0.680044 | +0.000000 | -6.082395 | 17 | 44 | 13 | +0.010796087 | +0.000000000 | complete | yes |
| [2](critical_buffer_fanout_32071_buf_28923-01/sta/metrics.json) | -0.931022 | -0.250978 | -10.658388 | 19 | 39 | 14 | +0.012216617 | +0.001420530 | complete | yes |
| [3](critical_buffer_fanout_32071_buf_17250-01/sta/metrics.json) | -0.679805 | +0.000240 | -6.656352 | 17 | 37 | 8 | +0.012199797 | +0.001403711 | complete | yes |

1. `critical_buffer_fanout_32071`: `ui_in[1] (input port clocked by clk)` to `_31996_ (rising edge-triggered flip-flop clocked by clk)`. Strict signoff: FAIL.
2. `critical_buffer_fanout_32071_buf_28923`: `ui_in[1] (input port clocked by clk)` to `_31995_ (rising edge-triggered flip-flop clocked by clk)`. Strict signoff: FAIL.
3. `critical_buffer_fanout_32071_buf_17250`: `ui_in[1] (input port clocked by clk)` to `_31995_ (rising edge-triggered flip-flop clocked by clk)`. Strict signoff: FAIL.

Best valid candidate by global setup WS: `critical_buffer_fanout_32071_buf_17250`.

Each candidate adds one separate buffer to the declared control; the candidates are not cumulative.
Best valid candidate improves control setup WS: True.

Old routed reference: WS -1.184761 ns, TNS -16.385711 ns, 23 endpoints, 28 slew and 6 fanout violations. Per-case deltas against this different routing history are retained in comparison.json.
