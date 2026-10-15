## Reverse engineering PIO and PRU

A processor is mostly controlled movement of data. Normal CPUs have things like caches, branch prediction, interrupts, etc, which make exact I/O timing hard to reason. 

A shift register is the bridge between moving bits across a wire and buses with 8,16,32 bits. With a hardware shafter plus an OUT instruction, the operation can collapse into one instruction per bit.

