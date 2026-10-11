# V0 regression

The ten cocotb tests exercise only the Tiny Tapeout external pins. Programs are
uploaded through the actual parallel host interface; tests do not force internal
memories or inspect hierarchy-dependent registers. They run at 50 MHz.

## Run

Install Icarus Verilog (`iverilog` and `vvp` on PATH) and Python 3.11 or newer:

```sh
python -m pip install -r test/requirements.txt
python test/run.py
```

Run that command from the repository root. The runner reads the source list from
`info.yaml` and returns failure for simulator errors, failed tests or missing tests.
This is also the convenient entry point on Windows without GNU Make.

On Windows, `./test/run.ps1` also selects the optional project-local Python and
Icarus tools in the ignored `.tools` directory when present, otherwise using
installed tools. It only changes PATH for the duration of the test run.

The original Makefile/CI entry point is supported:

```sh
make -C test
```

Both entry points produce `test/results.xml` and `test/tb.fst`.

## Coverage

- Reset defaults, instruction upload/readback, low-byte staging, held strobes,
  read latching, bus output enables and conflicting RD/WR.
- Full 16-bit scratch reads/writes, arithmetic overflow/underflow, logic/shift,
  taken and untaken branches, jump and halt.
- Exact WAIT timing for 0, 1, 7 and 4095 extra clocks; PC wrap at 32 words.
- Complete UART frames for `55`, `00`, `FF`, `A6` with dividers 0 (clamped), 1, 2,
  7 and 434; stores while busy; WAIT_TX and GPIO completion markers.
- The actual `examples/uart_v0.hex` program, loaded and read back through host pins.
- UART status polling, HALT while transmitting, divider capture, busy host writes,
  STOP/reset during a frame, START/restart and disabled bus behavior.
- Running instruction/data write protection, invalid opcode and invalid targets.

## Inspect the UART example

Run only the example to get a short capture (PowerShell):

```powershell
$env:COCOTB_TEST_FILTER = 'documented_uart_demo$'
python test/run.py
Remove-Item Env:COCOTB_TEST_FILTER
```

Or with a POSIX shell:

```sh
COCOTB_TEST_FILTER='documented_uart_demo$' python test/run.py
```

Open the waveform:

```sh
gtkwave test/tb.fst test/tb.gtkw
# or
surfer test/tb.fst
```

`tb.user_project.uart_tx_pin` is the TX waveform, also visible as `uo_out[0]`.
The saved GTKWave view includes host signals, PC, instruction, accumulator,
wait counter, UART busy and GPIO. Internal signals are useful for viewing RTL
but are not required by any test and may be absent in a gate-level netlist.

## Gate-level test

After hardening, copy the generated `tt_um_shanebri_top` netlist to
`test/gate_level_netlist.v`, set `PDK_ROOT` to the CMOS5L PDK and run:

```sh
make -C test -B GATES=yes
```

The existing GDS workflow also invokes the gate-level test. Local RTL tests and
generic synthesis do not establish physical area, routed timing or gate-level
correctness; those checks require the PDK and hardened netlist.

## Optional generic synthesis

With Yosys installed, run from the repository root:

```sh
yosys -p 'read_verilog -sv src/project.sv src/protocol_core.sv src/host_interface.sv src/execution_unit.sv src/uart_tx.sv src/frontend/pc.sv src/frontend/decoder.sv src/frontend/instruction_fetch.sv; synth -noabc -top tt_um_shanebri_top; check -assert; stat'
```

This checks synthesizability, driver consistency and mapped generic logic before
technology mapping. It is not an ASIC area estimate.
