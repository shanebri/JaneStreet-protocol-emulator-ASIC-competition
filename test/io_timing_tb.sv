`default_nettype none
`timescale 1ns/1ps
// Cycle differential test, including the reset edge that can corrupt unreset
// IMEM if reset is removed from command intent without a local write guard.
module io_timing_tb;
    reg clk=0, rst_n=0, ena=1;
    always #10 clk=~clk;
    reg [7:0] ui=0, din=0;
    wire [7:0] pins, dout, oe, ref_pins, ref_dout, ref_oe;
    tt_um_shanebri_top dut(ui,pins,din,dout,oe,ena,clk,rst_n);
    tt_um_shanebri_top_reference ref_dut(ui,ref_pins,din,ref_dout,ref_oe,ena,clk,rst_n);
    integer cycles=0, seed=32'h1921abcd, i, e, phase, a, value;
    reg checked=0;
    task tick; begin @(posedge clk); #2; end endtask
    task drive(input [7:0] control, input [3:0] nibble);
        begin @(negedge clk); ui=control; din[3:0]=nibble; tick(); end
    endtask
    task byte_write(input [3:0] addr, input [7:0] data);
        begin
            drive({4'h0,addr},0); drive({4'h1,addr},data[3:0]);
            drive({4'h0,addr},0); drive({4'h1,addr},data[7:4]);
        end
    endtask
    task word_write(input [7:0] selector, input [31:0] data);
        begin
            byte_write(5,selector); byte_write(6,data[7:0]);
            byte_write(7,data[15:8]); byte_write(9,data[23:16]); byte_write(10,data[31:24]);
        end
    endtask
    always @(posedge clk) begin
        #1;
        cycles=cycles+1;
        checked=1;
        if ({pins,dout,oe} !== {ref_pins,ref_dout,ref_oe})
            $fatal(1,"pin trace differs at cycle %0d",cycles);
        if ({dut.pio.selected_engine,dut.pio.owner} !==
            {ref_dut.pio.selected_engine,ref_dut.pio.owner})
            $fatal(1,"shared state differs at cycle %0d",cycles);
    end
    // Check combinational OE release as well as state after clock edges.
    always @(negedge clk) begin
        #1;
        if (checked && ({pins,dout,oe} !== {ref_pins,ref_dout,ref_oe}))
            $fatal(1,"between-edge pin trace differs");
        if (!rst_n && oe !== 0) $fatal(1,"reset did not release OEs immediately");
    end
    genvar g;
    generate for(g=0;g<2;g=g+1) begin: compare
        integer j;
        // Architectural and staged state, including invisible FIFO/IMEM words.
`define SAME(path) \
        if (dut.pio.engines[g].path !== ref_dut.pio.engines[g].path) \
            $fatal(1,"engine %0d state %s differs at cycle %0d",g,`"path`",cycles);
        always @(posedge clk) begin
            #1;
            `SAME(bank.imem_address) `SAME(bank.imem_low)
            `SAME(bank.data_address) `SAME(bank.data_stage) `SAME(bank.data_snapshot)
            `SAME(core.running) `SAME(core.fault)
            `SAME(core.x) `SAME(core.y) `SAME(core.osr) `SAME(core.isr)
            `SAME(core.out_count) `SAME(core.in_count) `SAME(core.current_pc)
            `SAME(core.delay_left) `SAME(core.divider) `SAME(core.divider_left)
            `SAME(core.shiftctrl) `SAME(core.execctrl) `SAME(core.pinctrl)
            `SAME(core.route) `SAME(core.filter_enable)
            `SAME(core.irq) `SAME(core.irq_waiting) `SAME(core.debug_flags)
            `SAME(core.exec_pending) `SAME(core.exec_instruction)
            `SAME(core.pins) `SAME(core.directions) `SAME(core.open_drain)
            `SAME(core.tx_fifo.level) `SAME(core.tx_fifo.read_ptr) `SAME(core.tx_fifo.write_ptr)
            `SAME(core.rx_fifo.level) `SAME(core.rx_fifo.read_ptr) `SAME(core.rx_fifo.write_ptr)
            for(j=0;j<4;j=j+1) begin
                `SAME(core.tx_fifo.words[j]) `SAME(core.rx_fifo.words[j])
            end
            for(j=0;j<32;j=j+1) begin `SAME(core.fetch.words[j]) end
        end
`undef SAME
    end endgenerate
    initial begin
        repeat(2) tick(); @(negedge clk); rst_n=1;
        // Load both engines with a FIFO loop and establish distinct retained RAM.
        for(e=0;e<2;e=e+1) begin
            byte_write(15,e); byte_write(2,0);
            byte_write(3,8'ha0); byte_write(4,8'h80); // PULL block
            byte_write(3,8'hc7); byte_write(4,8'ha0); // MOV ISR,OSR
            byte_write(3,8'h20); byte_write(4,8'h80); // PUSH block
            byte_write(3,0); byte_write(4,0);         // JMP 0
        end
        // Assertion at every nibble/gap phase and every byte address. In
        // particular address 4's final nibble presents IMEM intent at reset.
        for(e=0;e<2;e=e+1) for(a=0;a<16;a=a+1) for(phase=0;phase<4;phase=phase+1) begin
            byte_write(15,e);
            drive(a,0); drive(8'h10|a,4'h5); drive(a,0);
            @(negedge clk); rst_n=0;
            case(phase)
                0: begin ui=8'h10|a; din[3:0]=4'ha; end
                1: ui=8'h20|a;
                2: ui=8'h30|a;
                3: ui=a;
            endcase
            tick();
            @(negedge clk); rst_n=1; repeat(2) tick();
            // A held strobe after release cannot re-arm or replay the phase.
            drive(a,0);
        end
        // Exercise both execution and live host commands with minimum-gap bytes.
        for(i=0;i<1000;i=i+1) begin
            byte_write(15,i%2);
            case(i%10)
                0: word_write(8,$random(seed));
                1: word_write(8'h1c,3); // aligned group START
                2: begin byte_write(5,9); drive(8'h26,0); drive(6,0); drive(8'h26,0); end
                3: byte_write(12,$random(seed));
                4: byte_write(0,$random(seed));
                5: word_write(8'h14,$random(seed));
                6: word_write(8'h1b,$random(seed));
                7: word_write(i%32,$random(seed));
                8: begin @(negedge clk); ena=0; tick(); @(negedge clk); ena=1; end
                9: begin drive(8'h30,0); drive(0,0); end
            endcase
            din[7:4]=$random(seed); ui[7:6]=$random(seed);
        end
        // Adversarial address/direction changes, held strobes, enable and reset.
        for(i=0;i<10000;i=i+1) begin
            @(negedge clk);
            ui=$random(seed); din=$random(seed);
            ena=(i%19)!=0; rst_n=(i%113)!=0;
            tick();
        end
        $display("PASS: IO timing differential reference, reset-edge IMEM retention, %0d cycles",cycles);
        $finish;
    end
    initial begin #5000000; $fatal(1,"IO timing differential timeout"); end
endmodule
`default_nettype wire
