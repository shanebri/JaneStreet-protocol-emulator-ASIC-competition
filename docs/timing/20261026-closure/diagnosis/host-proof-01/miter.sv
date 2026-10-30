module host_miter(input clk,rst_n,ena,input [7:0] control,read_data,input [3:0] data_in,output mismatch);
reg initialized=0;
always @(posedge clk) if (!rst_n) initialized <= 1;
wire [49:0] g,c;
host_gold gold(.clk(clk),.rst_n(rst_n),.ena(ena),.control(control),.data_in(data_in),.read_data(read_data),.address(g[3:0]),.write_en(g[4]),.read_en(g[5]),.write_data(g[13:6]),.data_out(g[17:14]),.data_oe(g[21:18]),.write_intent(g[22]),.read_intent(g[23]),.word_write_intent(g[24]),.formal_state(g[48:25]),.formal_invariant(g[49]));
host_gate gate(.clk(clk),.rst_n(rst_n),.ena(ena),.control(control),.data_in(data_in),.read_data(read_data),.address(c[3:0]),.write_en(c[4]),.read_en(c[5]),.write_data(c[13:6]),.data_out(c[17:14]),.data_oe(c[21:18]),.write_intent(c[22]),.read_intent(c[23]),.word_write_intent(c[24]),.formal_state(c[48:25]),.formal_invariant(c[49]));
assign mismatch = initialized && (g != c);
endmodule
