# Buffered SRAM portal and candidate-specific timing closure

Status: **rejected, not currently viable under the no-regression contract; not
approved or promoted**. The clean normal production run stops at its parent-margin
acceptance gate. Active production remains the qualified
`bb7c5ef3c54a7ae2733bbfae82aa940016375007` implementation.

## Diagnosis

The rejected first integration has 13 failing slow setup endpoints: four engine-1
pin bits, four engine-1 direction bits, three inferred instruction-read-address
bits, engine-1 PC bit zero, and engine-0 direction bit three. Twelve paths start
at `ui_in[1]`; one starts at `ui_in[5]`. Exact source-state identities were verified
by re-emitting the original Yosys JSON with and without generated names and
requiring the regenerated mapped cells to match the archived synthesis netlist.
These are host acceptance/control to existing engine-state paths, not evidence
that an SRAM read arc is too slow.

The separate electrical inventory includes 47 violating pin records. Macro
`A_MEN` slew is 0.971224 ns against 0.595200 ns; `A_DIN[10]` slew is 0.716141 ns
against the same limit. Six SRAM outputs exceed their 0.064 pF cap limit, with
the worst at 0.103300 pF. Other violations cluster on weak standard-cell drivers
and branches above eight actual input loads, including antenna pins.

After the first candidate-specific repair the worst setup contribution shifts
to the live HOST_RD input's shared acceptance/control cone, ending at engine-1
direction bit two. All nine reported endpoints below 1 ns in that screen start
at `ui_in[5]`. Repairing only the original address-origin paths would leave this
competing cone as the limiter.

## Registered interface increment

The new candidate keeps deterministic instruction fetch, execution, engine FIFOs,
reset/enable behavior and package host timing. It changes only the experimental
host SRAM portal integration:

- Each bank captures portal word commits, operation and compressed payload into
  local registers. The central portal combines only qualified registered events;
  no live selected-engine data/selector mux feeds its request logic.
- The payload retains the low 16 bits and whether any upper bit was set, preserving
  full-word invalid-data/address/command rejection. Command admission is captured
  against the original busy/done state, including a completion-edge collision.
- Each bank registers a one-hot packet read selector alongside its existing
  selector write. Packet fields are read locally through the existing coherent
  snapshot boundary. Existing core/common-selector control is restored to its
  original expression rather than adding packet-range tests to engine writes.
- The portal accepts a captured command directly into the SRAM wrapper when
  ready, removing the redundant old pending stage. Only queued work needs the
  hold registers. Forwarding uses captured events, preserving metadata readback
  cycles without a combinational host-input-to-memory path.

A differential test against the old experimental integration passes **16,802
byte-side cycles** with identical SRAM issue cycles/address/data/direction and
host-visible reads, including reset, freeze, bank changes, every upper payload
bit, and a command on the exact completion edge. All **39 existing RTL tests**
pass, as do the existing unit/differential checks, 58 timing-tool tests and three
host API tests. A new package-pin SRAM test passes all 64 locations, bank-local
staging, errors, reset retention and simultaneous one-instruction-per-cycle
engine execution. That same test is included in candidate gate qualification.

The verified Metal3/Metal4 supply repair is retained. Native power connectivity
and the independent serialized supply/contact audit pass on this candidate.
No forbidden TopMetal1 or extra package pins are introduced.

## Measured physical increments

Every screen is compared with its matched control and with the passing production
parent. Failing screens are not qualified parents and are never promoted. Setup
changes below include actual routed parasitics, not placement estimates.

| Routed artifact | Slow setup ns | Slow slew | Cap violations | Fanout violations | Disposition |
| --- | ---: | ---: | ---: | ---: | --- |
| Qualified production parent | 0.303434 | 0 | 0 | 0 | Passing parent |
| Previous experimental SRAM integration | -0.756343 | 28 | 6 | 13 | Rejected |
| Registered portal, initial route | 0.070388 | 20 | 1 | 15 | Rejected |
| First matched reroute control | 0.160959 | 27 | 1 | 25 | Rejected |
| First measured repair | 0.223915 | 5 | 0 | 9 | Rejected |
| Second matched reroute control | 0.480812 | 4 | 0 | 12 | Rejected |
| Second measured repair | 0.449109 | 0 | 0 | 2 | Rejected: fanout remains |
| Clean normal production candidate | 0.110301 | 0 | 0 | 0 | Rejected: setup margin loss |

The first repair uses 95 transparent buffers on 59 uniquely bound sources and
five function-equivalent gate-strength changes. Macro-boundary buffers use
positions derived from the actual placed macro pins. Partial-sink repairs isolate
only declared macro inputs; an audit rejects any undeclared sink repartition.
The second repair adds 33 buffers on 11 measured sources and 15 gate-strength
changes to the actual post-first-repair netlist. Both audits preserve all original
signal connections and clock topology and verify strength functions against the
pinned PDK model. Only uniquely resolved structural identities may be mutated.

The second repair consumes setup margin versus its failing matched control:
**31.703 ps slow, 45.916 ps typical, 23.788 ps fast diagnostic**. It also consumes
2.773 ps slow hold and 1.167 ps typical hold; fast diagnostic hold improves by
16.559 ps. These costs are not hidden behind a green setup result. Some gain
between screen generations comes from rerouting alone, as the controls show.

Against the passing production parent, the second repair has these signed
headroom consumptions (parent minus candidate; negative means more margin):

| Corner | Setup ns | Hold ns |
| --- | ---: | ---: |
| Slow | -0.145675 | -0.291762 |
| Typical | -0.056369 | -0.174749 |
| Fast diagnostic | -0.043930 | -0.107233 |

Both remaining violations in the second repair screen are nine-load branches.
There are no setup, hold, slew or capacitance violations in that screen; it is
rejected. Its margins do not predict the clean production result below.

## Clean normal production result: rejected

The clean normal production run completes synthesis, placement, native power
connectivity, all three audited data repairs, native detailed routing and route
finalization, fill insertion and extracted three-corner STA. The additional
parent comparison then **rejects** it before route acceptance. Extracted setup,
hold, slew, capacitance and fanout violation counts are zero in all three
reported corners, but positive setup margin is insufficient under the user's
no-regression rule:

| Corner | Parent setup ns | Candidate setup ns | Setup headroom consumed ns | Candidate hold ns | Hold headroom consumed ns |
| --- | ---: | ---: | ---: | ---: | ---: |
| Slow | 0.303434 | 0.110301 | **+0.193133** | 0.650533 | -0.277412 |
| Typical | 6.120987 | 5.972638 | **+0.148349** | 0.312668 | -0.166917 |
| Fast diagnostic | 9.516462 | 9.449281 | **+0.067181** | 0.114340 | -0.101528 |

Negative hold consumption means increased hold margin. The exact comparison
records full precision and hashes both states. The clean build shows why the
better setup margin in an isolated screen cannot be treated as production
qualification. It is not justified to attribute the whole screen-to-production
difference to the final six buffers: the screen and production routing sequences
also differ.

The final worst slow path is again host address/control, `ui_in[1]` to
`pio.dirs[1][2]`, with 0.110301 ns slack. All eight reported endpoints below 1 ns
start at `ui_in[1]` and end in engine-1 pin/direction state. The first input
buffer drives 0.112218 pF with 0.710904 ns slew; the path also includes an
existing 0.655795 ns hold-delay cell and a long engine-control logic chain.
There is no SRAM access arc in this limiting path. Source identities are mapped
against the exact clean synthesis graph, and the final electrical inventory has
zero violating pins. This evidence still identifies shared host/control timing
as a limitation; changing the memory macro alone would not remove that cone.

Final native routing DRC and antenna counts are zero. Native finalization passes
connectivity/cell/placement equality and reports no serialized wire-contact
groups. Because production rejects setup-margin regression, **Magic GDS DRC,
GDS-extracted LVS, Tiny Tapeout precheck and the final routed-netlist gate
regression are not reached**. The earlier mapped-netlist smoke test and RTL
results are not substitutes for those checks. Production is not resumed past
the rejecting gate, and the candidate is not promoted. No active implementation
revert is needed: all candidate integration and repair work was isolated.

After rejection, a separate read-only diagnostic qualification of this exact
route completes all nine independent macro-aware STA sessions and reproduces
the native extracted metrics. All nine constraint-coverage reports are empty,
the full source-derived clock-pin set is identical (**2,580** sinks, including
the macro), no clock branch exceeds eight loads, and the independent final
wire-contact check passes. Die boundary and all 43 signal-pin geometries match
the production template. This diagnostic is stored outside the production
acceptance step; it does **not** waive the rejecting parent comparison or run
the GDS signoff tail.

## Repeatable candidate flow and remaining qualification

The clean candidate is frozen at
`test/sim_build/packet_sram_buffered_production_20261030_01/`. It uses the normal
pinned production entrypoint and the measured main/tail contracts. Final
post-antenna fanout correction measures current actual loads, excludes the full
clock tree, binds only overloaded data drivers, and buffers groups of at most
four. It cannot substitute obsolete numerical cell names from the old design.

The clean synthesis netlist SHA256 is
`f80426dd3eb02b283571686a22877566dfe51ad6e5f76d218334de2389cab5f4`,
identical to the registered-portal screen.
Both the main and first incremental contracts resolve uniquely in this clean
build, and both connectivity/function/clock-topology mutation audits pass.
After that reroute the measured remaining overloads are `_33834_/Q` and
`place7836/X`, each with nine actual input loads. These differ from the screen's
two residual branches, demonstrating why stale numerical targets cannot be
reused. The measured policy binds those exact current drivers and inserts six
buffers; its connectivity/function/clock-topology audit passes. Unchanged wires
are preserved with an independently checked connection/location audit before
native route finalization.

Candidate-only support retains strict checks and adds:

- Full source-derived sequential/macro clock-pin-set equality in final clock
  coverage instead of retaining the old hardcoded count of 2,421.
- Macro timing libraries loaded and hashed in independent replay, with missing
  or ambiguous corner mappings rejected. All nine sessions on an immutable prior
  artifact reproduce native extracted STA; the source clock audit also passes.
- Partial-sink transparency audits with tests rejecting foreign/duplicate sinks,
  undeclared repartition and macro clock buffering. Four new audit tests and the
  original 58 timing-tool tests pass on the overlaid tools.
- A parent-margin rejection gate before route acceptance. It rejects any loss
  of setup/hold margin or any electrical error relative to the exact passing
  CI state. The comparison still reports headroom consumption on failed results.
- The original 39 gate tests plus the new SRAM package-pin gate test, using the
  official functional macro model on the exact final netlist.

The mapped synthesis-netlist SRAM smoke test passes with the vendor model and
Nix Icarus 13, including concurrent engine execution. Its first launch stopped
before running assertions because embedded system Python could not load
`libexpat.so.1` in the Nix environment. Supplying the existing pinned Nix expat
library to the simulator subprocess fixes that runtime dependency; no RTL,
Liberty, layout or constraints are changed. This early smoke test is separate
from the required final routed-netlist regression.

Release qualification requires extracted all-corner timing/electrical checks,
coverage/replay, routing/Magic DRC, antenna, serialized geometry, GDS LVS, Tiny
Tapeout precheck, gate tests and the parent comparison. This run fails that
comparison. KLayout DRC remains outside
the established baseline scope. No acceptance limit, clock/I/O budget, uncertainty,
derate or load has been relaxed.

The available fast SRAM library remains characterized at -55 C, paired in these
diagnostics with -40 C standard cells. **Fast results here are diagnostic and
cannot establish exact -40 C SRAM compliance.** No temperature label or library
content is altered. Missing required characterization remains a separate release
block even if the physical implementation checks complete successfully.

A hashed inventory of all **30** available SRAM fast libraries in this pinned
PDK finds -55 C characterization for every one, including the alternative
single-port and dual-port macros, and zero exact 1.32 V / -40 C models. Changing
to another macro in this inventory does not resolve that particular blocker.
The inventory does not qualify those alternatives' timing, geometry or ports.

## Retained evidence

Compact evidence is in [buffered_portal_20261030/](buffered_portal_20261030/),
with file hashes in `evidence_sha256.json` and original full-report locations,
sizes and SHA256 values in `full_source_inventory.json`. Long timing reports
retain the first path and final lines; complete source reports remain in the
ignored frozen trial directories. `disposition.json` records frozen-input and
active-production identity checks and the original failed production job.
No passing physical-parent successor is claimed.
