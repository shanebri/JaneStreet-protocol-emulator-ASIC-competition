# Upstream data ECO comparison

All cases start from the same prepared input and use a matched full reroute. Positive slack deltas mean improvement. Screen validity does not imply strict signoff.

| Case | WS ns | Delta control | TNS ns | Endpoints | Slew | Fanout | Fast hold ns | Delta fast hold ns | Annotation | Valid screen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [1](critical_buffer_fanout_32071-01/sta/metrics.json) | -0.680044 | +0.000000 | -6.082395 | 17 | 44 | 13 | +0.010796087 | +0.000000000 | complete | yes |
| [2](critical_buffer_fanout_32071_acceptance_drive-01/sta/metrics.json) | -0.469818 | +0.210227 | -3.995197 | 17 | 24 | 11 | +0.012395307 | +0.001599221 | complete | yes |

1. `critical_buffer_fanout_32071`: `ui_in[1] (input port clocked by clk)` to `_31996_ (rising edge-triggered flip-flop clocked by clk)`. Strict signoff: FAIL.
2. `critical_buffer_fanout_32071_acceptance_drive`: `ui_in[1] (input port clocked by clk)` to `_31995_ (rising edge-triggered flip-flop clocked by clk)`. Strict signoff: FAIL.

Best valid candidate by global setup WS: `critical_buffer_fanout_32071_acceptance_drive`.

Each candidate applies its declared independent repair to the control; candidates are not cumulative.
Best valid candidate improves control setup WS: True.

Old routed reference: WS -1.184761 ns, TNS -16.385711 ns, 23 endpoints, 28 slew and 6 fanout violations. Per-case deltas against this different routing history are retained in comparison.json.
