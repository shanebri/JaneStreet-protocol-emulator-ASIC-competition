# Opt-in Arty USB low-speed SETUP/ACK bench build

Board qualification is pending. Enable the candidate explicitly with
`--usb-setup-ack`. The build receipt identifies this profile as
`usb-ls-setup-ack-opt-in`. This Arty image adds one independent USB low-speed link on JD. The
USB front end exposes asynchronous RCV/VP/VM receiver outputs and VPO/VMO
driver inputs with active-low output enable. The host bridge, its feeder,
both PIO engines and their pin assignments retain the revision-0x21 contract.
USB has no serial commands, payload buffer or software dependencies.

## Contract

- At 50 MHz the receiver synchronizes all three inputs. RCV tracks the
  differential polarity and VP/VM qualify SE0 or SE1 after 12 clocks to
  reject the USB low-speed crossover interval. It resynchronizes a 33⅓-clock bit sampler on
  J/K edges, checks SYNC, decodes NRZI and removes mandatory stuffed bits.
- Accept SETUP at address zero, endpoint zero, with a valid PID and CRC5.
  Only the immediately following valid DATA0 with exactly eight payload
  bytes and a valid CRC16 can trigger ACK. Expect that packet within 600
  core clocks of the token EOP. The transaction retains no payload.
- Recognize EOP as 40–90 qualified SE0 clocks followed by J. Long SE0,
  SE1, bad framing, missing stuff bits, bad CRC or unexpected packets
  invalidate the transaction. This is a prototype receiver window for
  the first bench transaction.
- After the qualified DATA0 SE0→J edge, wait 120 core clocks before
  driving ACK SYNC. Cancel if the line ceases to be idle during this
  wait. ACK occupies 19 bit cells including two SE0 cells and one J
  cell. TX uses a 33/33/34-clock cadence and releases the driver
  after the final J. The design target at the connector is
  1.33–4.33 µs from received SE0→J to reply J→K.
- Reset cancels receive, pending SETUP and transmit. The reset signal
  forces OE inactive even if the FPGA clock stops. Bus reset SE0
  invalidates pending receive state. While transmitting, ignore receive
  echo. Receive never backpressures the bus and drops invalid traffic
  without automatic reply or replay. The two PIO engines can run
  concurrently on their existing pins.

## Qualification references and budget

Source parent is merged feeder revision
8ed80e403bad39e2b36ec5ba3da46eea190234ae. Immediate physical parent and
active FPGA reference for this feature is the board-tested feeder image
b1d10fbefb043bcc4ab657220a0ee4ecfbcbd2b64eccb9a5b0f06b9c7ae0bc0b
(5.050 ns setup, 0.049 ns hold). Cumulative FPGA accounting uses the
October 30 fixed qualified image
eae65c98681b502283fa53732b4229626d2c81eef60da5c0945aa448c7986d15
(4.618 ns setup, 0.040 ns hold). The November 1 bridge is the
intermediate reference (4.871 ns setup, 0.047 ns hold).

The fixed ASIC release is bb7c5ef3c54a7ae2733bbfae82aa940016375007
(CI 40938542430). The active and immediate ASIC parent is the November 4
extracted state aecf268e7bda1242683b19d238f0f99ea469bf9b00b6df963e042b2d71802062.
USB logic lives in the FPGA wrapper, so all ASIC inputs and reserves
are inherited. See the [project status](project_status.md),
[headroom receipt](timing/20261104-headroom/activation.json) and
[feeder receipt](fpga_packet_feeder_receipt.json).

No new approved architecture floors were found. Evaluate all required
FPGA timing checks independently and keep zero required violations and TNS.
Proposed promotion floors are 4.618 ns setup and 0.040 ns hold in the
applicable Vivado summary, based on the fixed Arty build. Require both
max and min checks on each new PHY output and preserve legacy XDC and CDC
coverage. These are proposed engineering budgets. Keep the parent image
available and require approval and the physical USB transaction before
selecting the candidate. Treat parent differences within 0.000001 ns as
ties only when raw report precision supports that distinction.

## Bench setup

Build into a fresh directory. The option includes the packet feeder.

```sh
python -B tools/bringup/build.py --usb-setup-ack --out .bringup/usb-ls-setup-ack/new
mkdir -p test/sim_build
iverilog -g2012 -s usb_ls_setup_ack_tb -o test/sim_build/usb-setup-ack.vvp fpga/usb_ls_setup_ack.sv test/usb_ls_setup_ack_tb.sv
vvp test/sim_build/usb-setup-ack.vvp
```

| Arty JD | FPGA | Front end |
| --- | --- | --- |
| JD1 | D4, input | VP |
| JD2 | D3, input | VM |
| JD3 | F4, output | VPO |
| JD4 | F3, output | VMO |
| JD7 | E2, output | Active-low OE |
| JD8 | D2, input | RCV, high for D+ greater than D− |

A TUSB1106-class transceiver can provide the interface. Follow its peripheral
circuit for VBUS power, termination and attach, with 3.3 V digital I/O, common
ground, low-speed slew, VPO/VMO driver mode and the low-speed pull-up on D−.
Keep OE pulled high at the transceiver while the FPGA is unconfigured.
Connect the USB cable to the transceiver's bus side.
[TI transceiver datasheet](https://www.ti.com/lit/ds/symlink/tusb1106.pdf),
[Digilent pin assignments](https://raw.githubusercontent.com/Digilent/digilent-xdc/master/Arty-A7-100-Master.xdc)

### Measure ACK and driver release

1. Probe D+ and D− separately at the device-side USB connector and probe
   active-low OE at the transceiver input (JD7). Use high-impedance probes
   with short ground connections to USB ground. Trigger on OE falling.
   Start with a roughly 25 µs acquisition and at least 5 µs of pretrigger.
2. After bus reset and recovery, send SETUP to address 0, endpoint 0,
   followed by DATA0 containing `80 06 00 01 00 00 12 00`. A standard
   host's first enumeration attempt can provide a valid SETUP/DATA0 pair.
   The prototype only completes that transaction. A low-speed host
   exerciser provides repeatable payloads and error injection.
3. Find the DATA0 EOP (both lines low, then low-speed J with D− high).
   Place the first cursor on SE0→J and the second on the first J→K of ACK
   SYNC (D+ high). Both cursors belong on the USB line traces. Target
   **1.33–4.33 µs** and check that the PID decodes as ACK (`0xD2`).
4. At ACK's own EOP, verify two SE0 bit cells, followed by one driven J
   cell. Measure from that SE0→J edge to OE rising. The RTL schedules
   release after **660 ns** for that final cell, and the pin-to-pin
   measurement includes front-end and FPGA output delays. Idle J persists
   through the pull-up. OE rising marks the disable command. Check that
   the next legal host packet has normal line swing while OE stays high
   to verify bus handoff.
5. Save the three-channel traces with feeder traffic idle and active.
   If available, capture the feeder's marker on a fourth channel to show
   overlap. Use the exerciser to send bad CRC and wrong-address cases.
   Trigger on the incoming packet for those cases and confirm OE stays
   high through the reply window.

[USB 2.0 specification, §§7.1.4.1 and 7.1.18.1](https://www.usb.org/document-library/usb-20-specification),
[TI transceiver datasheet](https://www.ti.com/lit/ds/symlink/tusb1106.pdf)

## Routed candidate and budget ledger

Vivado 2026.1, part xc7a100tcsg324-1, unchanged 50 MHz clock and legacy XDC.
The native all-corner summary reports 3.835 ns max and 0.048 ns min slack,
with zero failing endpoints, TNS, THS or pulse-width violations. Independent
read-only reporting split the same routed checks into Slow and Fast views.
The table retains Vivado's 0.001 ns reported precision. Equal printed values
cannot establish a tie at the policy's 0.000001 ns tolerance.

Overall slack, in ns. Positive consumption means slack decreased. The
first proposal used floors of 4.618 max and 0.040 min across the whole
summary. No architecture floors are approved.

| Corner | Check | Fixed | Parent | Candidate | Parent consumed | Fixed consumed | First proposed floor | Remaining |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Slow | Max | 4.618 | 5.050 | 3.835 | 1.215 | 0.783 | 4.618 | −0.783 |
| Slow | Min | 0.158 | 0.171 | 0.171 | 0.000 | −0.013 | 0.040 | 0.131 |
| Fast | Max | 12.999 | 13.039 | 10.222 | 2.817 | 2.777 | 4.618 | 5.604 |
| Fast | Min | 0.040 | 0.049 | 0.048 | 0.001 | −0.008 | 0.040 | 0.008 |

The new max limiter is the synchronized reset button through the OE gating
LUT to JD7. Its Slow arrival is 11.165 ns against the new 15.000 ns output
limit. The actual 50 MHz register-to-register group still has 5.277 ns Slow
and 13.184 ns Fast setup. The Slow intra-clock limiter is engine 1 PC to TX
FIFO write enable. The Fast min limiter is the observer input register to
trace BRAM, replacing the parent's feeder data to completion-sequence path.
Rerouting can move these limits. No matched control was used to attribute
the legacy path changes to the USB logic.

A group-specific promotion proposal is to keep the original proposal for the
comparable 50 MHz group and review PHY outputs against their separate
15 ns max and 0 ns min digital I/O requirements. This retains the original
constraints and makes the added output path visible without comparing it to
a different path group's 20 ns requirement. Connector timing and electrical
qualification are separate acceptance conditions.

| Corner | Group/check | Parent | Candidate | Proposed floor | Remaining |
| --- | --- | ---: | ---: | ---: | ---: |
| Slow | 50 MHz setup | 5.050 | 5.277 | 4.618 | 0.659 |
| Slow | 50 MHz hold | 0.171 | 0.171 | 0.040 | 0.131 |
| Fast | 50 MHz setup | 13.039 | 13.184 | 4.618 | 8.566 |
| Fast | 50 MHz hold | 0.049 | 0.048 | 0.040 | 0.008 |
| Slow | PHY output max | — | 3.835 | 0.000 | 3.835 |
| Slow | PHY output min | — | 4.731 | 0.000 | 4.731 |
| Fast | PHY output max | — | 10.222 | 0.000 | 10.222 |
| Fast | PHY output min | — | 1.769 | 0.000 | 1.769 |

In the 50 MHz group, fixed-reference setup consumption is −0.659 ns Slow and
−0.185 ns Fast. Hold consumption is −0.013 ns Slow and −0.008 ns Fast. The
fixed release had no PHY output paths. The candidate adds 174 LUTs and 108
registers relative to the feeder parent, with seven BRAM tiles in both images.

### ASIC ledger

Parent and candidate ASIC are the same extracted state. Incremental
consumption is zero. Values below are in ns and rounded for display. Raw
values are in the activation receipt. Required ASIC architecture floors
remain unassigned.

| Corner | Parent and candidate setup / hold | Cumulative setup / hold consumed vs fixed ASIC release |
| --- | ---: | ---: |
| Slow | 0.532949699 / 0.561024798 | −0.229515968 / −0.187904697 |
| Typical | 6.249411832 / 0.264246299 | −0.128425274 / −0.118495994 |
| Fast | 9.689972654 / 0.089365851 | −0.173510988 / −0.076554432 |

### Qualification and identities

- RTL pin simulation covers valid requests, ±1.5% host clock offset,
  a 210 ns crossover, bad address and endpoint, PID, CRC5, CRC16, stuffing,
  short/long EOP, wrong data toggle and length, expiry, reset and OE release.
  The four complete replies started 2.466–2.477 µs after modeled input EOP.
- The same USB bench passed on the full routed Arty functional netlist
  using Vivado XSIM and vendor primitive models. The bench drove the USB
  pins through the top-level buffers and checked the MMCM and synchronized
  button reset path. The model used functional primitive timing. Connector
  timing remains a physical bench measurement.
- The existing 39 core tests, six feeder serial tests and four build-tool
  tests passed. The standalone RTL USB bench also runs in streaming CI.
- Zero route errors and DRC findings. CDC reports 17 safe endpoints, zero
  unsafe, unknown or missing ASYNC_REG endpoints. Timing coverage reports
  zero unclocked registers and unconstrained internal endpoints. The three
  added async inputs are cut only to the first-stage synchronizers and each
  of the three PHY outputs has a constrained max and min path.
- Candidate bitstream SHA-256
  `04c964fe9377fef36a0f44797bc1ce6228d8ffedd6a727165004e91386f7ee77`.
  Routed checkpoint SHA-256
  `0cb9a4731ae88185dfb32cf8e94b918e7ed276a823542c4269ce89aee6e9e741`.
  Build receipt SHA-256
  `8fa2f4134156fdb3975199c165d1cdb520433caeb1ce3acfac739ff3e67e9f2b`.
  Full routed functional netlist SHA-256
  `09d379195927b6572cc5eacdad673dc9c89476037bf86f5cf66249884d052c26`.
  Bench source SHA-256
  `422cb307369a0028874d41a9c6b19be4b530ccafa4c276924fe5943ea1552054`.
  Local artifacts are in `.bringup/usb-ls-setup-ack/route-04`, with
  checkpoint evidence in `.bringup/usb-ls-setup-ack/routed-evidence`.
  The receipt binds the modified source files as well as the source parent.

**Disposition: opt-in FPGA bench build.** The new PHY output met its actual
15 ns constraint but missed the first whole-design proposed max floor.
Promotion needs an approved budget decision and the physical transceiver
capture, including connector timing, OE release, and coexistence with
active feeder traffic. The feeder reference remains available.
