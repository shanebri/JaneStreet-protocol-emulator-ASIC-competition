> Historical checkpoint or task record. Status statements and next steps below
> apply to the named revision/date. See [current project status](project_status.md)
> for the qualified dual-engine build and remaining hardware work.

# Timing closure hypotheses — research only, 2026-10-25

No RTL, synthesis configuration, constraints, physical database or acceptance
gate was changed for this investigation. No new synthesis or physical repair
was run. New findings below come from read-only inspection of the existing
85506c6 archive, pinned tool sources and PDK, plus the official competition and
tool documentation. Earlier measured experiments remain in
[timing_experiments_20261024.md](timing_experiments_20261024.md).

## Recommendation

The strongest current hypothesis is that closure needs a combination of
timing-oriented mapping, timing-driven placement and selective extracted-load
repair. The evidence does not yet require a different instruction latency or a
replacement architecture. If implementation improvements leave large deficits,
the strongest RTL targets are retirement/FIFO control and instruction predecode.
No proposed option is a proven fix before a routed experiment.

The unchanged design fails slow setup by 6.809803 ns across 616 endpoints, with
TNS -979.921111 ns. This is too broad to promise closure by resizing one gate.
The previous best physical-only WNS gain was only 0.324652 ns, with worse TNS.
Those trials started after placement or at CTS; they did not explore a different
technology mapping or timing-driven global placement.

## Constraints and competition scope

Preserve the project's recorded confirmed 8x4 allocation, IHP CMOS5L, 20 ns clock,
both engines, all required corners, host acceptance edges and one-cycle ordinary
instruction retirement. Keep programmable behavior, instruction coverage,
FIFO ordering/backpressure, reset/enable semantics and pin/OE behavior intact.

The [official Jane Street challenge](https://blog.janestreet.com/protocol-emulator-asic-competition/)
asks for a programmable general-purpose protocol emulator. It does not prescribe
this project's exact PIO microarchitecture or a 50 MHz clock. Those remain project
requirements. The public page retrieved today still lists 6x4 and describes 8x4
as a prospective increase; it does not independently verify the project's
recorded 8x4 confirmation. Preserve that confirmation with submission records.
No area increase is proposed here.

## New evidence that changes the ranking

All archived paths below are relative to
`/home/shane/eda/timing-20261024/current/runs/wokwi/` in Ubuntu-24.04 WSL.

1. **The mapped design was optimized for area at the typical corner.**
   `resolved.json` records `SYNTH_STRATEGY="AREA 0"`, `SYNTH_CORNER=null`,
   `DEFAULT_CORNER="nom_typ_1p20V_25C"`, `SYNTH_ABC_BUFFERING=false`, and
   `SYNTH_SIZING=false`. `06-yosys-synthesis/yosys-synthesis.log` confirms the
   typical Liberty models were loaded. Pinned `steps/pyosys.py` confirms that an
   unset synthesis corner selects the default corner.
2. **Timing-driven placement was disabled.** `resolved.json` has
   `PL_TIMING_DRIVEN=false`, with routability-driven placement enabled.
   The installed `steps/openroad.py` and `scripts/openroad/gpl.tcl` support
   enabling timing-driven placement. This is a verified available option,
   not an assumption based on newer documentation. The actual placement log
   loads only the typical corner. With `PNR_CORNERS=null`, this installed base
   step selects `[DEFAULT_CORNER]`; its variable description says otherwise.
   Resizer steps separately override this and load all three corners. Therefore
   explicitly checking optimization-corner selection matters, even though final
   signoff already includes slow.
3. **A critical single-load net makes a substantial routing detour.** In
   `44-openroad-detailedrouting/tt_um_shanebri_top.def`, `_23246_` is at
   (336.960, 453.600) um and `_33839_` at (757.440, 457.380) um.
   Summing the centerline wire segments of net `_01516_` gives 1253.22 um:
   Metal2 34.92, Metal3 421.08, Metal4 797.22. Its routed pin access points are
   approximately 422.34 um Manhattan distance apart. The route travels down
   near y=62.58 um before returning to the destination. This is approximately
   a 3x detour; it is not a claim that delay scales linearly with length.
4. **The same net has an expensive electrical consequence.** Extracted STA
   reports 0.178745 pF, 3.561205 ns delay through `sg13cmos5l_nor4_1`, and
   4.579258 ns output slew. The receiving flop's setup requirement is
   1.067971 ns at the reported transition. Reducing load can improve both driver
   delay and receiving setup requirements; the achievable gain is unmeasured.
5. **Other critical connections are also long.** Net `_10727_`, between a mux
   and downstream logic on the worst path, has 529.38 um routed wire. The path
   contains 17 `buf_1` cells contributing 8.783121 ns. These are distributed
   through the path, not one removable chain of 17 redundant buffers.
6. **Low utilization does not mean routing is uncongested.** The global-route
   log reports residual overflow of 2 on Metal2 and 178 on Metal3, and warns that
   routing finished with congestion. Signal routing is limited to Metal2–Metal4.
   The report establishes local congestion, not that congestion alone caused
   every detour. No use of an additional metal layer is proposed.
7. **There are stronger legal cells available.** The pinned slow Liberty
   includes `nor4_2` and buffer strengths 1, 2, 4, 8 and 16. These are absent
   from the PDK synthesis/PNR exclusion lists. This establishes candidate cell
   availability, not that every size is the best choice at every location.
8. **Automatic repair did not exhaust the solution space.** Post-placement
   electrical repair inserted 2715 buffers in 604 nets and resized zero cells.
   Post-CTS setup repair reported no setup violations under its estimated
   parasitics, then inserted 2767 hold buffers. Final extracted setup still
   failed. These counts justify examining estimation and buffer topology;
   they do not justify deleting hold buffers or asserting a tool bug.

The resizer logs load all three required corners and final STA checks all three.
Typical-corner synthesis does not imply missing slow-corner signoff. Intermediate
state files also carry inherited metrics: some slow-corner entries in later
states are unchanged older values while the new intermediate report is typical
only. Use fresh per-corner reports for comparisons, never inherited summary
fields as evidence of intermediate timing improvement.

## Ranked hypotheses

### 1. Improve placement and repair the measured long, weakly driven nets

**Structure:** the PC/fetch control feedback cone, its fanout distribution,
terminal next-state logic and the destination state. Start with `_01516_`,
`_10727_` and the high-delay buffer segments, then all failing path families.

**Proposal:** test timing-driven placement from the existing synthesis result.
Then separately test explicit inclusion of the slow corner in placement's
optimization views, preferably all three existing views, checking tool support
and the emitted library-loading log. Enabling the timing flag alone would
otherwise retain typical-only placement views in this pinned flow.
Separately test a small extracted-load ECO: stronger terminal NOR, or a buffer
that isolates it from the long wire, plus selective local placement/routing
repair. Rebuild inefficient distribution branches only where load and slack
justify it. Keep fanout limits and legal routing layers unchanged.

**Why:** this directly attacks observed wire capacitance, slow transitions and
time spent distributing control. Timing-driven placement can prioritize critical
nets before CTS and routing lock in poor geometry. OpenROAD documents timing
weighting and resizer interaction in its
[placement documentation](https://openroad.readthedocs.io/en/latest/main/src/gpl/README.html).

**Tradeoff/hazards:** some added cell area and power; stronger cells load their
inputs more; moving one gate can lengthen other inputs; faster data can violate
fast hold. Narrowing an engine's placement too aggressively can worsen congestion.

**Confidence:** high that this targets measured defects; medium for material
timing improvement; insufficient evidence for closure by itself. Even eliminating
the entire 3.56 ns terminal gate delay would not recover the full deficit, before
considering setup-time changes and alternative critical paths.

### 2. Map the logic for delay, including the failing slow corner

**Structure:** the full flattened, area-mapped combinational network, including
fetch/decode, control, register enables and host/FIFO paths.

**Proposal:** independently compare `DELAY 4` and a simpler delay strategy such
as `DELAY 0` against `AREA 0`; then compare the synthesis corner on the promising
strategy. The pinned version supports these choices. Its `DELAY 4` script
explicitly includes buffering, upsizing and downsizing. Keep sequential ABC
optimization off initially to avoid expanding the equivalence problem.

Using `SYNTH_CORNER=nom_slow_1p08V_125C` selects an existing verified model for
optimization; it does not alter that model or remove typical/fast signoff.
Avoid conflating strategy, corner and placement changes in the first comparisons.

**Why:** repeated weak gates and expensive shared distribution are plausible
consequences of the existing mapping choices. Area is approximately 30.6% of the
core, giving some cell-area headroom, although routing headroom must be measured.
The [LibreLane configuration reference](https://librelane.readthedocs.io/en/latest/reference/step_config_vars.html)
describes the strategy/corner distinction; the installed source was checked to
avoid relying on changed defaults in current online documentation.

**Tradeoff/hazards:** potentially more logic, clock-independent power, fanout and
congestion. Slow-corner mapping may create fast-corner hold problems. A better
synthesis slack can become a worse routed result, as the failed fetch trial showed.

**Confidence:** medium-high that this is an important untested lever; medium
that it produces a useful candidate; no guaranteed recovery amount.

### 3. Shorten and localize instruction retirement and FIFO acceptance logic

**RTL structures:** `protocol_core.sv` combines fetched/injected instruction,
`stall`, `illegal`, `halt`, `attempt` and `retire`; retirement qualifies both PC
advance and many state updates. `rx_room = !rx_full || (host_rx_pop && !rx_empty)`
feeds instruction stalling, which feeds retirement, RX push and FIFO storage.
`pio_fifo.sv` then qualifies push/pop with full/empty and reset/clear priority.

**Proposal:** compute per-instruction completion conditions and possible next-PC
values in parallel, then use shallow final selection. Separate local PC,
datapath, FIFO and pad commit conditions where their Boolean functions permit it.
Duplicate small late control terms near consumers instead of distributing one
shared result through several fanout-buffer stages. Derive direct RX acceptance
equations that preserve full-plus-simultaneous-pop behavior.

**Why:** the worst current path is address-state feedback; the failed fetch
candidate exposed a host-input-to-RX-FIFO path. Both are consistent with deep
shared completion/commit logic. Internal ABC names were stripped, so exact
ownership of each reported gate is still unproved: obtain cone correspondence
before choosing the first source expression to change.

**Tradeoff/hazards:** extra local logic and upstream load; synthesis can merge
duplicates again. Preserve atomic stalled instructions, side-set, illegal/HALT,
EXEC PC behavior, START/STOP priorities, IRQ and simultaneous FIFO operations.
Moving the critical path to data selection is a possible outcome.

**Confidence:** medium; stronger architectural evidence than a shifter rewrite,
but greater verification burden than the first two hypotheses.

### 4. Store instruction predecode alongside program memory

**Proposal:** when the host writes a complete instruction, also store selected
static metadata: opcode class, legality and relevant operand/destination classes.
Read it alongside the original word so execution does not repeatedly decode
those fields after the memory selection. Preserve the original host-visible
instruction words and all write acceptance edges. Decode dynamic EXEC injections
when they enter the pending-instruction register, with equivalent metadata.

**Why:** this moves computation to an existing write/capture boundary rather
than adding an execution stage. It is different from the failed AND/OR-tree read
experiment, which changed the memory mux without removing execution decode work.

**Tradeoff/hazards:** 8–16 metadata bits per word would add 512–1024 stored bits
across two 32-word engines, before optimization, plus read muxes and clock load.
Select fields by actual cone evidence; do not widen every instruction blindly.
Unreset IMEM/metadata must remain coherent across reset and writes, including
same-edge write visibility, stopped configuration changes and dynamic EXEC.
More stored bits might worsen routing enough to erase the benefit.

**Confidence:** medium as a promising latency-preserving architecture option;
lower confidence in net physical benefit than the narrower control rewrite.

### 5. Explore one-hot or banked PC/fetch organization only if fetch remains dominant

A true 32-state one-hot execution address could replace binary address decode
and some increment/wrap selection. It adds 27 state bits per engine if replacing
five binary bits, or 32 if retaining a redundant binary PC. Computed branch
targets still require decoding; host PC readback, wrap, restart and EXEC must
remain exact. Physical banking could keep small groups of instruction words and
their selection logic together.

This is not just another balanced OR expression. It changes state encoding and
locality, with corresponding formal invariants. The previous read-tree failure
lowers confidence in memory-only repair. Confidence: low-medium until better
mapping/placement and control repairs establish the remaining path.

### 6. Precompute configuration-derived masks and selectors

`pin_mask`, routing bases and threshold interpretations depend on configuration
that is normally written while stopped. Maintaining derived state at those
existing configuration edges could remove arithmetic/mux levels from execution
without extra instruction cycles. All source-register updates and reset defaults
must update the derived state atomically, including START interactions.

This is lower priority: current mapped evidence does not establish pin-mask or
shift logic as the primary bottleneck, and output timing currently passes.

## Required companion repair and lower-priority alternatives

The measured CTS branch recipe eliminated all 174 clock-buffer fanout failures,
but left seven data-fanout failures and did not close setup. Integrate it only
after understanding interactions with a promising candidate; clock repair is an
acceptance requirement, not the expected source of a 6.8 ns setup recovery.

Ordinary pipelining, multi-cycle execution, SRAM instruction fetch, fewer engines
or a slower clock might support a competition entry with a revised architecture.
They are not drop-in repairs under this project's existing behavior. A prefetch
pipeline alone cannot promise one-cycle taken arbitrary branches or dynamic EXEC;
the branch dependency must be handled explicitly. A synchronous SRAM is not
automatically faster for the current two-read-port asynchronous interface.
These remain fallback redesigns requiring a new functional contract.

Useful-skew tuning is low priority given the large data-path deficit and small
fast hold margin. Do not delete hold buffers, waive reset timing, increase fanout
limits, add unproved exceptions, or change PDK/RC models to make reports pass.

## Proposed experimental order, not executed

1. Smallest mechanism test: repair only the terminal NOR/long net using extracted
   load evidence, reroute and re-extract. Compare the same path and all competing
   path classes. This tests electrical leverage, not full closure.
2. Highest-value broad physical trial: enable timing-driven placement from the
   original synthesized netlist; keep all other design settings fixed. Follow
   with a separate placement-corner comparison including slow, rather than
   assuming that the final signoff corner list controls the placer.
3. Independent mapping trials: compare delay strategies, then synthesis corner,
   and physically evaluate promising survivors. Do not rank by synthesis WNS alone.
4. Combine only individually understood improvements, including clock fanout
   repair, and inspect remaining register/reset/per-port path families.
5. If large logic-depth deficits remain, implement one localized completion/
   FIFO-control rewrite; predecoded instruction storage follows only if justified.

For every implemented candidate: equivalence/differential checks appropriate to
the change, complete functional tests, fresh extracted three-corner setup/hold,
TNS/counts, slew/cap/fanout, coverage and area/congestion comparison. Functional
timing, reset and host acceptance must remain exact. Final acceptance additionally
requires completed gate tests, DRC/LVS/antenna and Tiny Tapeout precheck.

**Finding:** several high-value levers remain untested, including a disabled
timing-driven placer and an area/typical-corner synthesis choice. The data support
a focused implementation strategy; they do not establish an inevitable
architectural limit or a guaranteed single repair.
