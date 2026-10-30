`timescale 1ns/1ps
module portal_differential_tb;
    reg clk=0;
    always #10 clk=~clk;
    reg rst_n=0,enable=1,wr=0,rd=0;
    reg [3:0] address=0;
    reg [7:0] data=0;
    reg [5:0] pin_in=0;
    wire [7:0] current_read,reference_read;
    wire [11:0] current_pins,reference_pins;
    wire [3:0] current_dirs,reference_dirs,current_od,reference_od;
    pio_subsystem dut(.clk(clk),.rst_n(rst_n),.enable(enable),.host_address(address),
        .host_write_en(wr),.host_read_en(rd),.host_write_data(data),.pin_in(pin_in),
        .host_read_data(current_read),.pins(current_pins),.directions(current_dirs),.open_drain(current_od));
    packet_reference reference(.clk(clk),.rst_n(rst_n),.enable(enable),.host_address(address),
        .host_write_en(wr),.host_read_en(rd),.host_write_data(data),.pin_in(pin_in),
        .host_read_data(reference_read),.pins(reference_pins),.directions(reference_dirs),.open_drain(reference_od));
    integer cycles=0,i,j;
    reg [31:0] value;
    reg [31:0] random_state=32'h731ad45;
    always @(posedge clk) begin
        cycles=cycles+1;
        if (rd && current_read!==reference_read)
            $fatal(1,"byte read mismatch cycle %0d address %h current=%h reference=%h",cycles,address,current_read,reference_read);
        if (dut.packet.storage.memory.A_MEN!==reference.packet.storage.memory.A_MEN)
            $fatal(1,"macro issue cycle changed at %0d",cycles);
        if (dut.packet.storage.memory.A_MEN &&
            {dut.packet.storage.memory.A_ADDR,dut.packet.storage.memory.A_DIN,dut.packet.storage.memory.A_WEN,dut.packet.storage.memory.A_REN} !==
            {reference.packet.storage.memory.A_ADDR,reference.packet.storage.memory.A_DIN,reference.packet.storage.memory.A_WEN,reference.packet.storage.memory.A_REN})
            $fatal(1,"macro transaction changed at %0d",cycles);
        #1;
        if ({current_pins,current_dirs,current_od}!=={reference_pins,reference_dirs,reference_od})
            $fatal(1,"engine/pad state changed at %0d",cycles);
    end
    task cycle(input bit w,input bit r,input [3:0] a,input [7:0] d);
        begin @(negedge clk); wr=w; rd=r; address=a; data=d; @(posedge clk); #2; end
    endtask
    task word(input [7:0] selector,input [31:0] d);
        begin cycle(1,0,5,selector); cycle(1,0,6,d[7:0]); cycle(1,0,7,d[15:8]);
            cycle(1,0,9,d[23:16]); cycle(1,0,10,d[31:24]); end
    endtask
    task read_word(input [7:0] selector);
        begin cycle(1,0,5,selector); cycle(0,1,6,0); cycle(0,1,7,0);
            cycle(0,1,9,0); cycle(0,1,10,0); end
    endtask
    initial begin
        repeat(3) cycle(0,0,0,0);
        @(negedge clk); rst_n=1;
        for(i=0;i<64;i=i+1) begin
            cycle(1,0,15,i[0]); word('h21,i); read_word('h21);
            word('h22,16'ha500 ^ i); read_word('h22);
            word('h23,2); read_word('h20); read_word('h24); word('h23,4);
        end
        for(i=63;i>=0;i=i-1) begin
            cycle(1,0,15,i[0]); word('h21,i); word('h23,1);
            read_word('h20); read_word('h24);
            word('h23,1); read_word('h20); word('h23,4);
        end
        // Every command payload and upper-bit rejection, with no idle byte cycles.
        for(i=0;i<32;i=i+1) begin
            word('h23,i); read_word('h20); word('h23,4);
            word('h21,32'h10000+i); read_word('h21); read_word('h20); word('h23,4);
            word('h22,32'h10000+i); read_word('h22); read_word('h20); word('h23,4);
        end
        // A new command committing on the exact completion edge is rejected,
        // and a bank change immediately after commit cannot retarget a request.
        word('h23,4); word('h21,12); word('h22,16'hbeef); word('h23,2);
        cycle(1,0,6,1); cycle(1,0,7,0); cycle(1,0,9,0); cycle(1,0,10,0);
        read_word('h20); read_word('h24); word('h23,4);
        word('h23,1); cycle(1,0,15,1); read_word('h20); read_word('h24); word('h23,4);
        // Every upper payload bit must retain the original rejection behavior.
        for(i=16;i<32;i=i+1) begin
            value=32'd1<<i;
            word('h21,value); read_word('h21); read_word('h20); word('h23,4);
            word('h22,value); read_word('h22); read_word('h20); word('h23,4);
            word('h23,value|1); read_word('h20); word('h23,4);
        end
        // Freeze between commit and issue, then resume or reset at each phase.
        for(i=0;i<8;i=i+1) begin
            word('h21,i); word('h22,i); word('h23,2);
            @(negedge clk); enable=0;
            repeat(i+1) read_word('h20);
            @(negedge clk); enable=1;
            read_word('h20); read_word('h24); word('h23,4);
            word('h23,1); repeat(i) cycle(0,0,0,0);
            @(negedge clk); rst_n=0; cycle(0,0,0,0);
            @(negedge clk); rst_n=1;
            read_word('h20); read_word('h21); read_word('h24);
        end
        // Abandoned staging and rapid bank/selector changes remain coherent.
        for(j=0;j<300;j=j+1) begin
            random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
            cycle(1,0,15,random_state[0]);
            word('h21,random_state[5:0]);
            if(random_state[2]) word('h22,random_state[15:0]);
            word('h23,random_state[1] ? 1 : 2);
            read_word('h20); read_word('h24); word('h23,4);
        end
        cycle(0,0,0,0);
        $display("PASS portal differential: %0d byte cycles; exact macro issue/data, snapshots, bank switches, reset and freeze",cycles);
        $finish;
    end
    initial begin #10000000; $fatal(1,"timeout"); end
endmodule
