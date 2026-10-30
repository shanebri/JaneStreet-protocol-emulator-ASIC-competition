# Documentation guide

Start with [project status and qualification](project_status.md) for the current
design, exact passing ASIC build, timing margins and outstanding hardware work.
The root [README](../README.md) is the entry point for users.

## Current reference

- [Datasheet and host registers](info.md)
- [ISA and assembler syntax](isa.md)
- [Per-engine architecture/reset/transport contract](pio21_contract.md)
- [Dual-engine selection, ownership and group commands](dual_pio.md)
- [Host split decision](adr_four_bit_host.md)
- [Memory architecture and future SRAM options](memory_architecture.md)
- [Packet SRAM candidate, interface and qualification gate](packet_sram/implementation.md)
- [Buffered SRAM portal diagnosis and physical repair evidence](packet_sram/buffered_portal_20261030.md)
- [UART example](../examples/uart_v0.asm), [SPI guide](spi_mode0.md), [I2C guide](i2c.md)

## Build, verification and board use

- [Simulation, unit tests and gate-netlist instructions](../test/README.md)
- [FPGA demos and integration options](../fpga/README.md)
- [Repeatable Python bring-up suite and its limits](../tools/bringup/README.md)
- [October 30 physical FPGA smoke baseline and evidence receipt](fpga_baseline_20261030.md)
- [Fixed SPI/Nano hardware harness](../tools/spi_hardware/README.md)
- [Fixed UART demo monitor](../tools/UART_CLIENT.md)
- [Final route/LVS repair](timing_lvs_closure_20261029.md)
- [Register timing coverage audit](timing_coverage_audit_20261029.md)

## Historical records and design proposals

The revision-0x20 [optimization report](pio_v0_optimization_report.md),
single-engine [revision-0x21 verification matrix](pio21_verification.md),
[dual-engine implementation record](dual_pio_verification.md), and
[area budget](architecture_area_budget.md) retain their original snapshots.
Current results are summarized in the status page; historical test counts and
negative timing values describe their named revisions, not today's qualification.

The [dual-engine proposal](dual_pio_design_proposal.md) is implemented;
[I2C implementation prompt](i2c_implementation_prompt.md) is archived task input.
The [I/O timing investigation](io_timing_report.md),
[plan](io_timing_implementation_plan.md), [local experiment](io_timing_implementation.md)
and [candidate failure assessment](io_timing_failure_assessment.md) precede closure.
Other dated `timing_*.md` files and the Astra closure prompt are historical
experiment/handoff records. Their local paths may require the original work
directories. The [timing evidence tree](timing/README.md) retains frozen reports;
do not modify those measurements to describe later implementations.

Files under `notes/` are working research notes, not architecture contracts or
qualification reports. Local-only notes and ignored build outputs are not
required to follow the current setup guides.
