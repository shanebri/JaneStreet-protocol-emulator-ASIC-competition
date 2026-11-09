`default_nettype none
// Two slots share the public byte bus. A TX word is the arbitration quantum.
module packet_feeder_bank #(parameter integer MAX_ACTIVE_CYCLES=500000) (
    input wire clk, reset,
    input wire cmd_valid, cmd_slot, cmd_engine, cmd_both,
    input wire [2:0] cmd,
    input wire [31:0] cmd_data,
    input wire [15:0] cmd_length_minus_one,
    output wire cmd_ready,
    input wire query_slot,
    input wire [1:0] query,
    output reg [31:0] query_data,
    output wire busy,
    output reg [5:0] bus_request,
    output reg [7:0] bus_write_data,
    input wire [7:0] bus_read_data,
    input wire bus_done
);
    wire [2:0] states [0:1];
    wire [31:0] sequences [0:1];
    wire [1:0] results [0:1];
    wire [5:0] sent [0:1], requests [0:1];
    wire [7:0] statuses [0:1], levels [0:1], errors [0:1], writes [0:1];
    wire [1:0] ready, engines, atomic_word;
    reg [1:0] worker_done;
    wire collision = cmd == 3 && states[!cmd_slot] == 3 && engines[!cmd_slot] == engines[cmd_slot];
    wire both_ready = cmd == 3 && ready[0] && ready[1] && engines[0] != engines[1];
    assign cmd_ready = cmd_both ? both_ready : ready[cmd_slot] && !collision;
    assign busy = states[0] == 3 || states[1] == 3;
    genvar slot;
    generate for (slot=0;slot<2;slot=slot+1) begin: slots
        packet_feeder #(.MAX_ACTIVE_CYCLES(MAX_ACTIVE_CYCLES)) worker (
            .clk(clk),.reset(reset),.cmd_valid(cmd_valid && cmd_ready && (cmd_both || cmd_slot == slot)),
            .cmd(cmd),.cmd_data(cmd_data),.cmd_length_minus_one(cmd_length_minus_one),
            .cmd_engine(cmd_engine),.engine(engines[slot]),.cmd_ready(ready[slot]),
            .slot_state(states[slot]),.completion_sequence(sequences[slot]),.result(results[slot]),
            .words_sent(sent[slot]),.terminal_status(statuses[slot]),
            .terminal_levels(levels[slot]),.terminal_errors(errors[slot]),
            .bus_request(requests[slot]),.bus_write_data(writes[slot]),
            .bus_read_data(bus_read_data),.bus_done(worker_done[slot]),.bus_atomic(atomic_word[slot])
        );
    end endgenerate
    always @* begin
        case (query)
            0: query_data = {26'd0,engines[query_slot],results[query_slot],states[query_slot]};
            1: query_data = sequences[query_slot];
            2: query_data = {2'd0,errors[query_slot],levels[query_slot],statuses[query_slot],sent[query_slot]};
            3: query_data = MAX_ACTIVE_CYCLES;
        endcase
    end

    localparam [2:0] IDLE=0, SELECT=1, SELECT_IDLE=2, ACCESS=3, ACCESS_IDLE=4;
    reg [2:0] state;
    reg owner, turn, locked, lock_owner, bank_valid, selected_engine;
    wire candidate = locked ? lock_owner : (requests[turn] != 0 ? turn : !turn);
    always @(posedge clk) begin
        if (reset) begin
            state<=IDLE; owner<=0; turn<=0; locked<=0; lock_owner<=0;
            bank_valid<=0; selected_engine<=0; worker_done<=0;
            bus_request<=0; bus_write_data<=0;
        end else case (state)
            IDLE: begin
                if (!busy) bank_valid<=0;
                if (locked && !atomic_word[lock_owner]) begin
                    locked<=0; turn<=!lock_owner;
                end else if (requests[candidate] != 0) begin
                    owner<=candidate;
                    if (atomic_word[candidate]) begin locked<=1; lock_owner<=candidate; end
                    if (requests[candidate] != 6'h1f &&
                            (!bank_valid || selected_engine != engines[candidate])) begin
                        bus_request<=6'h1f; bus_write_data<={7'd0,engines[candidate]}; state<=SELECT;
                    end else begin
                        bus_request<=requests[candidate]; bus_write_data<=writes[candidate]; state<=ACCESS;
                    end
                end
            end
            SELECT: if (bus_done) begin
                bus_request<=0; bank_valid<=1; selected_engine<=engines[owner]; state<=SELECT_IDLE;
            end
            SELECT_IDLE: if (!bus_done) begin
                bus_request<=requests[owner]; bus_write_data<=writes[owner]; state<=ACCESS;
            end
            ACCESS: if (bus_done) begin
                if (bus_request == 6'h1f) begin bank_valid<=1; selected_engine<=engines[owner]; end
                bus_request<=0; worker_done[owner]<=1; state<=ACCESS_IDLE;
            end
            ACCESS_IDLE: if (requests[owner] == 0 && !bus_done) begin
                worker_done[owner]<=0;
                if (!atomic_word[owner]) begin locked<=0; turn<=!owner; end
                state<=IDLE;
            end
            default: state<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
