# Sink_local data ECO comparison

All cases start from the same prepared input and use a matched full reroute. Positive slack deltas mean improvement. Screen validity does not imply strict signoff.

| Case | WS ns | Delta control | TNS ns | Endpoints | Slew | Fanout | Fast hold ns | Delta fast hold ns | Annotation | Valid screen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [1](balanced_acceptance_electrical-01/sta/metrics.json) | 0.053006 | +0.000000 | 0.000000 | 0 | 12 | 5 | +0.011201429 | +0.000000000 | complete | yes |
| [2](electrical_sink_local-01/sta/metrics.json) | 0.239242 | +0.186235 | 0.000000 | 0 | 0 | 4 | +0.010718537 | -0.000482892 | complete | yes |

1. `balanced_acceptance_electrical`: `ui_in[5] (input port clocked by clk)` to `_31995_ (rising edge-triggered flip-flop clocked by clk)`. Strict signoff: FAIL.
2. `electrical_sink_local`: `ui_in[5] (input port clocked by clk)` to `_31996_ (rising edge-triggered flip-flop clocked by clk)`. Strict signoff: FAIL.

Best valid candidate by global setup WS: `electrical_sink_local`.

Each candidate applies its declared independent repair to the control; candidates are not cumulative.
Best valid candidate improves control setup WS: True.

Old routed reference: WS -1.184761 ns, TNS -16.385711 ns, 23 endpoints, 28 slew and 6 fanout violations. Per-case deltas against this different routing history are retained in comparison.json.
