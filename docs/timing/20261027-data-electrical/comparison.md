# Electrical data ECO comparison

All cases start from the same prepared input and use a matched full reroute. Positive slack deltas mean improvement. Screen validity does not imply strict signoff.

| Case | WS ns | Delta control | TNS ns | Endpoints | Slew | Fanout | Fast hold ns | Delta fast hold ns | Annotation | Valid screen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [1](critical_buffer_fanout_32071_balanced_acceptance-01/sta/metrics.json) | 0.252523 | +0.000000 | 0.000000 | 0 | 40 | 9 | +0.012208623 | +0.000000000 | complete | yes |
| [2](balanced_acceptance_electrical-01/sta/metrics.json) | 0.053006 | -0.199517 | 0.000000 | 0 | 12 | 5 | +0.011201429 | -0.001007194 | complete | yes |

1. `critical_buffer_fanout_32071_balanced_acceptance`: `ui_in[5] (input port clocked by clk)` to `_31995_ (rising edge-triggered flip-flop clocked by clk)`. Strict signoff: FAIL.
2. `balanced_acceptance_electrical`: `ui_in[5] (input port clocked by clk)` to `_31995_ (rising edge-triggered flip-flop clocked by clk)`. Strict signoff: FAIL.

Best valid candidate by global setup WS: `balanced_acceptance_electrical`.

Each candidate applies its declared independent repair to the control; candidates are not cumulative.
Best valid candidate improves control setup WS: False.

Old routed reference: WS -1.184761 ns, TNS -16.385711 ns, 23 endpoints, 28 slew and 6 fanout violations. Per-case deltas against this different routing history are retained in comparison.json.
