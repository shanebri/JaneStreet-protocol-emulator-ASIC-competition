# Timing evidence for 37c74dc

These small files retain source excerpts and derived arithmetic from the completed
[build](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/39495891524).
Read the [report](../../io_timing_report.md) and [implementation plan](../../io_timing_implementation_plan.md)
for interpretation and limitations.

Source artifact: [GDS_logs, ID 12307955521](https://github.com/shanebri/JaneStreet-protocol-emulator-ASIC-competition/actions/runs/39495891524/artifacts/12307955521).
ZIP SHA-256: `a81d874ee1a4e65360ed533e6b86530e3d685aa13a0d4e6434cf035e7f517e23`.
Commit: `37c74dc17c3803d30d7b225aa51da10f0809330c`.

All paths in the following table are relative to the artifact's `runs/wokwi/`.

| Retained file | Source / transformation |
| --- | --- |
| `worst_reset_setup.rpt` | First complete path from `55-openroad-stapostpnr/nom_slow_1p08V_125C/max.rpt`. |
| `reported_register_setup.rpt` | Worst register-launched path present in that same top-1,000 report. This is not an independently restricted register-only STA run. |
| `summary.rpt` | `55-openroad-stapostpnr/summary.rpt`, copied unchanged. |
| `effective.sdc` | `final/sdc/tt_um_shanebri_top.sdc`, copied unchanged. Evidence only, not installed as project constraints. |
| `electrical_checks.rpt` | Slew/fanout/capacitance section of slow-corner `checks.rpt`. |
| `netlist_excerpt.v.txt` | Selected cells from `final/nl/tt_um_shanebri_top.nl.v`, with original line numbers. Not a compilable netlist. |
| `config_excerpt.json` | Selected keys from `resolved.json`; original values retained. |
| `analysis.json` | Per-corner counts and worst startpoint summaries parsed from each `max.rpt`; slow worst-path delay partition. |
| `SHA256SUMS.txt` | SHA-256 of retained files, excluding this manifest itself. |

## Reproducing the analysis

Split each `max.rpt` at `Startpoint:`; read its `Endpoint:` and final `slack`
line. Count negative-slack paths, distinct endpoints and startpoints. Each corner
has 1,000 detailed paths. In the slow report, 821 distinct endpoints are negative
and all select `rst_n`. Independently count the `setup in-reg` lines in
`violator_list.rpt`: the same 821 entries sum to -2071.482457 ns at printed
precision, agreeing with full-precision TNS -2071.482472 ns to better than
0.001 ns. This validates the extracted list, not every alternative launch path.

For the first path, stop at the first `data arrival time`. Add the incremental
`Delay` values on cell-output rows (the rows carrying a fanout/capacitance value):
22.076864 ns in 48 cells. Of those, 26 `sg13cmos5l_buf_*` outputs sum to
12.972890 ns. Add cell-input incremental delays for explicit net propagation:
0.338129 ns. Keep the primary-port modeled input-driver delay, 0.003887 ns,
separate. Adding the external input budget of 4 ns reproduces 26.418880 ns
arrival within rounding. Do not sum cumulative `Time` values or include capture
clock arcs in the data-path partition.

Endpoint `_32168_` has Q connected to `pio.engines[1].core.isr[3]`. Its
asynchronous `RESET_B` connects to `net4538`, driven by a tie-high cell; the
reported reset path is to D, not an asynchronous recovery/removal check.

The full extracted archive remains an ignored local build product under
`test/sim_build/timing_review_37c74dc/`. No altered constraints or implementation
results are present in these evidence files.
