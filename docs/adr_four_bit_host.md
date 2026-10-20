# Decision: permanent four/four UIO split

Accepted for revision 0x21. Four UIO pins carry synchronous low-first host
nibbles; four belong exclusively to the protocol state machine. This permits
host service and abort during shared-wire WAIT/FIFO stalls without electrical
ownership handoffs. Byte acceptance remains a separate adapter boundary.

The execution core owns 12 value bits and four writable direction bits. A small
capability layer maps dedicated outputs and applies open-drain behavior only to
capable pads. Physical input synchronization is independent of execution enable.
Additive routing fields preserve UART/SPI binaries and old PINCTRL meanings.
Open-drain and filtered physical readback support I2C without a protocol FSM.

The cost is two host beats per byte and extra routing/input state. Four-word FIFO
depth does not fix sustained service deficits. Future burst transports can replace
the byte adapter; future FIFO/state-machine/pad changes require separate designs.
No crossbar, DMA, new memory architecture, multiple state machines or Ethernet/USB
is introduced. The 8x4 tile and 50 MHz targets remain subject to physical validation.

See [the contract](pio21_contract.md), [I2C ABI](i2c.md), and
[verification matrix](pio21_verification.md) for exact semantics and evidence.

The approved [dual-PIO extension](dual_pio.md) now adds a second independent
engine, banked host contexts and static output ownership. It preserves the
permanent four/four split and the original byte acceptance boundary. Other
deferred features above remain outside the implementation.
