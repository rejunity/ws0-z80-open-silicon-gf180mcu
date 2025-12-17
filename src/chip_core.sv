// SPDX-FileCopyrightText: © 2025 XXX Authors
// SPDX-License-Identifier: Apache-2.0

`default_nettype none

// TODO: rename or split file from chip_core.sv to ws_z80.v

module chip_core #(
    parameter NUM_INPUT_PADS,
    parameter NUM_BIDIR_PADS
    )(
    `ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
    `endif
    
    input  wire clk,       // clock
    input  wire rst_n,     // reset (active low)
    
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
    output wire [NUM_BIDIR_PADS-1:0] bidir_pd    // Pull-down
);

    // See here for usage: https://gf180mcu-pdk.readthedocs.io/en/latest/IPs/IO/gf180mcu_fd_io/digital.html

    assign bidir_cs = '0;
    assign bidir_sl = '0;
    assign bidir_ie = ~bidir_oe; // @TODO: disable inputs when data and address bus are floating (RESET, BUSAK)
    assign bidir_pu = '0;
    assign bidir_pd = '0;
    
    logic _unused;
    assign _unused = &{input_in[NUM_INPUT_PADS-1 : 9],
                       bidir_in[NUM_BIDIR_PADS-1 : 8]};

    // control wires
    wire busak_n = bidir_out[24 + 7];

    // 8 bidirectional data bus pins
    wire data_oe;
    assign bidir_oe[7:0]        = {8{data_oe}};                     // 1 = Output | 0 = Input


    // 16 output address bus pins
    assign bidir_oe[8+:16]      = {16{1'b1 && rst_n && busak_n}};   // 1 = Output | 0 = Input - ADDRESS bus is floating during RESET and BUSAK

    // 8 output control pins
    assign bidir_oe[24 + 0]     = 1'b1;                             // 1 = Output             - M1 always output
    assign bidir_oe[25 +:4]     = { 4{1'b1          && busak_n}};   // 1 = Output | 0 = Input - MREQ, RD, WR, IORQ are floating ONLY during BUSAK (see: Figure 10 BUS Request/Acknowledge Cycle)
    assign bidir_oe[29 +:3]     = { 3{1'b1}};                       // 1 = Output             - RFSH, HALT, BUSAK always output

    // No pull-ups neither for 1) original Z80 input pins, 2) nor for configuration pins (which are not part of the original Z80), 3) nor for unused pins
    //                            - for both INT and BUSREQ it is explicitly stated in the Z80 Manual "requires an external pull-up for these applications"
    //                            - for NMI and WAIT there is nothing in the Z80 Manual, but we assume they were implemented electrically similar to INT and BUSREQ
    assign input_pu = '0;
    // No pull-downs since the original Z80 input pins are active LOW and should NOT be pulled down
    assign input_pd[3:0] = '0;

    // Set configuration pins (not part of the original Z80) to 0s, pull-downs ON
    assign input_pd[8:4] = '1;
    // Set the rest of input pull-downs ON
    assign input_pd[NUM_INPUT_PADS-1:9] = '1; // LukeW: I'd recommend a pull-down
                                              // otherwise pads can float up to mid rail and
                                              // start drawing current.
                                              // The pulls are pretty weak, like 100k or so.


    z80 z80 (
        .clk     (clk),
        .cen     (1'b1),
        .reset_n (rst_n),

        // 4 input control pins
        .wait_n  (input_in[0]),
        .int_n   (input_in[1]),
        .nmi_n   (input_in[2]),
        .busrq_n (input_in[3]),

        // NOTE: The original Z80 has a peculiar data bus pin order, keep it to minimize wire crossing on the DIP40 PCB
        // Also see: http://www.righto.com/2014/09/why-z-80s-data-pins-are-scrambled.html
        .di      ({bidir_in [7:0]}),
        .dout    ({bidir_out[7:0]}),
        .doe     (data_oe),
        .A       ({bidir_out[23:8]}),

        .halt_n  (bidir_out[24 + 6]),
        .busak_n (bidir_out[24 + 7]),
        .m1_n    (bidir_out[24 + 0]),
        .mreq_n  (bidir_out[24 + 1]),
        .iorq_n  (bidir_out[24 + 2]),
        .rd_n    (bidir_out[24 + 3]),
        .wr_n    (bidir_out[24 + 4]),
        .rfsh_n  (bidir_out[24 + 5]),
        
        .early_signals(input_in[8:4])
    );


    // EXAMPLE: the following code is example from the original template
    // logic [NUM_BIDIR_PADS-1:0] count;

    // always_ff @(posedge clk) beginf
    //     if (!rst_n) begin
    //         count <= '0;
    //     end else begin
    //         if (&input_in) begin
    //             count <= count + 1;
    //         end
    //     end
    // end

    // logic [7:0] sram_0_out;

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
