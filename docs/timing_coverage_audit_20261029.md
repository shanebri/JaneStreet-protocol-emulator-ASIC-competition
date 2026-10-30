# Timing coverage audit: successful GitHub GDS build

Audited run: [40938542430](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/40938542430), commit `bb7c5ef3c54a7ae2733bbfae82aa940016375007`.
Evidence: `GDS_logs` artifact 12938512721, SHA256
`d4324384dc97112bf01ec3097c76cba63ce80cfb30319e702fa9ec5526bcf719`.

## Conclusion

The optional native register-to-register setup summary is misleading. Its
`Infinity` is not evidence of unconstrained registers. Restricted register STA
reports have finite positive setup slack in all three corners. The exact archived
netlist, nominal SPEF and SDC reproduce the issue locally in OpenSTA.
No RTL, constraints, PDK, or production flow changes were needed for this audit.

## Root cause and reproduction

The installed pinned LibreLane script is
`/nix/store/6a08ghhhzl5a07nr0ly762yh1ah6m5bj-python3-3.13.13-env/lib/python3.13/site-packages/librelane/scripts/openroad/sta/corner.tcl`.
Lines 327–341 initialize worst register setup slack to `1e30`, call
`find_timing_paths -unique_paths_to_endpoint -path_delay max -sort_by_slack
-group_path_count 999999999 -slack_max 1e30`, and only afterward filter for
`reg-reg` paths. Line 347 emits the resulting metric. The native STA logs emit
`inf`, serialized as `"Infinity"` in state JSON.

Selecting a single worst path per endpoint before restricting its startpoint
can discard every register-origin path when input paths dominate those endpoints.
Increasing the group path limit cannot recover the discarded alternatives.

A direct slow-corner reproduction using the archived netlist, SDC and SPEF,
the matching local slow standard-cell Liberty and OpenSTA 2.7.0 returned:

```
AUDIT unrestricted unique-endpoint classification: in 2429 out 16
AUDIT restricted register setup slack: 0.988909
```

The reproduction uses the same `get_nets ... == "NULL"` classification as the
native script. The unrestricted selection contains no `reg-reg` path. A query
restricted with `-from [all_registers -clock_pins] -to [all_registers -data_pins]`
before path selection returns a real register path. The result matches the
independent restricted report already produced by the GitHub build. This audit
reran the slow corner locally; all-corner values below come from archived CI STA.

The installed `clock.rpt` formatter has a separate typo at lines 378–379: for a
propagated clock it sets `is_virtual` instead of `is_propagated`. Thus its
`Virtual: yes / Propagated: no` header is also misleading. The effective SDC
explicitly sets propagated clocks, `unpropagated.rpt` is empty, and the restricted
reports include the physical launch/capture clock tree delays.

## Restricted register timing

Archived `70-pio-routeacceptance/qualification/replay/<corner>-baseline/`
reports query register clock pins to register data pins directly.

| Corner | Register setup slack (ns) | Register hold slack (ns) |
| --- | ---: | ---: |
| Slow 1.08 V, 125 C | 0.988909 | 0.373120 |
| Typical 1.20 V, 25 C | 8.026990 | 0.145750 |
| Fast 1.32 V, -40 C | 12.118178 | 0.012811 |

The worst register setup path is `_33837_` to `_31995_`, both rising-edge
flip-flops clocked by `clk`. The operational sessions, which case-analyze reset
inactive, give the same worst register setup values. These restricted setup
results are distinct from the overall slow setup slack of 0.303434 ns, which
belongs to a host-input path.

## Constraint coverage

- The archived effective SDC defines one 20 ns clock on `clk`, 0.25 ns clock
  uncertainty, 0.15 ns transition and propagated clock analysis.
- All 18 non-clock input ports have 4 ns input delays. All 24 output ports,
  including all output enables, have 4 ns output delays and 6 fF loads.
- The SDC includes early/late timing derates of 0.95/1.05. It has no false-path,
  multicycle, disabled-timing or clock-group exceptions.
- All nine `coverage.rpt` files (three corners times baseline, operational and
  reset-active modes) are empty. The generating command checks unconstrained
  endpoints, multiple clocks, missing clocks/input delays, loops and generated
  clocks. The production qualification wrapper rejects nonempty coverage reports.
- Baseline keeps reset and enable dynamic. Operational/reset-active cases are
  supplementary diagnostics. Slow baseline reset-rise/fall setup slacks are
  6.888617/6.927267 ns; reset is not silently removed from the baseline analysis.
- Independent clock connectivity audit reports 2,421 sequential clock sinks.
- All corners have zero filtered parasitic annotation gaps and zero reported
  setup/hold violations. The strict signoff checker does not use the optional
  native register summary as passing evidence.

These results establish coverage under the specified synchronous I/O contract.
They do not establish board-level timing, asynchronous-input metastability MTBF,
or arbitrary asynchronous reset-release safety.

## Disposition

Close the `Infinity` investigation as a summary path-selection artifact.
Use the restricted reports for register setup margin; retain full coverage and
overall setup/hold checks. A future reporting improvement should select register
startpoints/endpoints before calculating the register summary, and fail explicitly
if an expected register path is absent. The native tool script was not patched.
No implementation rebuild is required solely to resolve this finding.

Local reproduction inputs/script/log are retained in
`test/sim_build/github_analysis_40938542430/`; the original CI reports remain in
the linked Actions artifact.
