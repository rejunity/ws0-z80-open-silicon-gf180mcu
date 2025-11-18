// SPDX-FileCopyrightText: © 2025 XXX Authors
// SPDX-License-Identifier: Apache-2.0

`default_nettype none

// TODO: rename or split file from chip_core.sv to ws_z80.v

module chip_core #(
    parameter NUM_INPUT_PADS,
    parameter NUM_BIDIR_PADS,
    parameter NUM_ANALOG_PADS
    )(
    `ifdef USE_POWER_PINS
    inout wire VDD,
    inout wire VSS,
    `endif
    
    input  logic clk,                            // clock
    input  logic rst_n,                          // reset (active low)
    
    input  wire [NUM_INPUT_PADS-1:0] input_in,   // Input value
    output wire [NUM_INPUT_PADS-1:0] input_pu,   // Pull-up
    output wire [NUM_INPUT_PADS-1:0] input_pd,   // Pull-down

    input  wire [NUM_BIDIR_PADS-1:0] bidir_in,   // Input value
    output wire [NUM_BIDIR_PADS-1:0] bidir_out,  // Output value
    output wire [NUM_BIDIR_PADS-1:0] bidir_oe,   // Output enable
    output wire [NUM_BIDIR_PADS-1:0] bidir_cs,   // Input type (0=CMOS Buffer, 1=Schmitt Trigger)
    output wire [NUM_BIDIR_PADS-1:0] bidir_sl,   // Slew rate (0=fast, 1=slow)
    output wire [NUM_BIDIR_PADS-1:0] bidir_ie,   // Input enable
    output wire [NUM_BIDIR_PADS-1:0] bidir_pu,   // Pull-up
    output wire [NUM_BIDIR_PADS-1:0] bidir_pd,   // Pull-down

    inout  wire [NUM_ANALOG_PADS-1:0] analog     // Analog
);

    // See here for usage: https://gf180mcu-pdk.readthedocs.io/en/latest/IPs/IO/gf180mcu_fd_io/digital.html
    
    // Disable pull-up and pull-down for input
    assign input_pu = '0;

    assign bidir_cs = '0;
    assign bidir_sl = '0;
    assign bidir_ie = ~bidir_oe;
    assign bidir_pu = '0;
    assign bidir_pd = '0;
    
    logic _unused;
    assign _unused = &bidir_in;



    // NOTE: The original Z80 has a peculiar data bus pin order, keep it to minimize wire crossing on the DIP40 PCB
    // Also see: http://www.righto.com/2014/09/why-z-80s-data-pins-are-scrambled.html

    // @TODO: float A, D on reset
    // @TODO: float A, D, MREQ, RD, WR, IORQ pins on BUSAK (Figure 10 BUS Request/Acknowledge Cycle)

    // 8 bidirectional data bus pins
    assign bidir_oe[7:0]        
                                = {8{data_oe}}; // 1 = Output | 0 = Input


    // 16 output address bus pins
    assign bidir_oe[8+:16]      
                                = {16{1'b1}};   // 1 = Output

    // 8 output control pins
    assign bidir_oe[24+:8]
                                = {8{1'b1}};    // 1 = Output

    // set the rest of bidir as output and drive them low
    assign bidir_oe[NUM_BIDIR_PADS-1:32] = '1;
    assign bidir_out[NUM_BIDIR_PADS-1:32] = '0;

    // @TODO: investigate original Z80 if pull-down/pull-up should be attached to the inputs
    // input pull-downs off
    assign input_pd[3:0] = '0;
    // default configuration pins to all 0s, pull-downs ON
    assign input_pd[8:4] = '1;
    // set the rest of input pull-downs off
    assign input_pd[NUM_INPUT_PADS-1:9] = '0;


    wire data_oe;
    z80 z80 (
        .clk     (clk),
        .cen     (1'b1),
        .reset_n (rst_n),

        // 4 input control pins
        .wait_n  (input_in[0]),
        .int_n   (input_in[1]),
        .nmi_n   (input_in[2]),
        .busrq_n (input_in[3]),

        .di      ({bidir_in [0], bidir_in [1], bidir_in [2], bidir_in [3], bidir_in [4], bidir_in [5], bidir_in [6], bidir_in [7]}),
        .dout    ({bidir_out[0], bidir_out[1], bidir_out[2], bidir_out[3], bidir_out[4], bidir_out[5], bidir_out[6], bidir_out[7]}),
        .doe     (data_oe),
        .A       ({bidir_out[8+:16]}),

        .halt_n  (bidir_out[24 + 0]),
        .busak_n (bidir_out[24 + 1]),
        .m1_n    (bidir_out[24 + 2]),
        .mreq_n  (bidir_out[24 + 3]),
        .iorq_n  (bidir_out[24 + 4]),
        .rd_n    (bidir_out[24 + 5]),
        .wr_n    (bidir_out[24 + 6]),
        .rfsh_n  (bidir_out[24 + 7]),
        
        .early_signals(input_in[8:4])
    );


    // EXAMPLE: the following code is example from the original template
    // logic [NUM_BIDIR_PADS-1:0] count;

    // always_ff @(posedge clk) begin
    //     if (!rst_n) begin
    //         count <= '0;
    //     end else begin
    //         if (&input_in) begin
    //             count <= count + 1;
    //         end
    //     end
    // end

    // logic [7:0] sram_0_out;

    // (* keep *)
    // gf180mcu_fd_ip_sram__sram512x8m8wm1 sram_0 (
    //     `ifdef USE_POWER_PINS
    //     .VDD  (VDD),
    //     .VSS  (VSS),
    //     `endif

    //     .CLK  (clk),
    //     .CEN  (1'b1),
    //     .GWEN (1'b0),
    //     .WEN  (8'b0),
    //     .A    ('0),
    //     .D    ('0),
    //     .Q    (sram_0_out)
    // );

    // logic [7:0] sram_1_out;

    // (* keep *)
    // gf180mcu_fd_ip_sram__sram512x8m8wm1 sram_1 (
    //     `ifdef USE_POWER_PINS
    //     .VDD  (VDD),
    //     .VSS  (VSS),
    //     `endif

    //     .CLK  (clk),
    //     .CEN  (1'b1),
    //     .GWEN (1'b0),
    //     .WEN  (8'b0),
    //     .A    ('0),
    //     .D    ('0),
    //     .Q    (sram_1_out)
    // );

    // assign bidir_out = count ^ {24'd0, sram_0_out, sram_1_out};

endmodule

`default_nettype wire
