// SPDX-FileCopyrightText: © 2025 Project Template Contributors
// SPDX-License-Identifier: Apache-2.0

`default_nettype none


// Wafer space padring
// - 56 pads are for internal signals,
// - 18 pins are dedicated to power supply and their locations CAN NOT be changed!
//
// Layout here matches orientation of the GDSII. Pads are numbered counter-clockwise.
// Note that the actual orientation chip on PCB might be different.
//
//                    52  50  48  46  44  42  40  38
//                  53| 51| 49| 47| 45| 43| 41| 39| 37
//                  | | | | | | | | | | | | | | | | |
//           ,------v-v-v-v-v-v-v-v---v-v-v-v-v-v-v-v-------.
//           |                      G                       |
//     54 -->|                      N                   VDD |+-- 36
//     55 -->|                      D                   GND |--- 35
//     56 ---| GND                                      VDD |+-- 34
//     57 --+| VDD                                      GND |--- 33
//     58 -->|                                              |<-> 32
//     59 -->|                                              |<-> 31
//     60 -->|                                              |<-> 30
//     61 -->|                      |                       |<-> 29
//     62 ---| GND                WAFER                     |<-> 28
//     63 --+| VDD               -SPACE-                    |<-> 27
//     64 -->|                    GF180                 GND |--- 26
//     65 -->|                      |                   VDD |+-- 25
//     66 -->|                                              |<-> 24
//     67 -->|                                              |<-> 23
//     68 -->|                                              |<-> 22
//     69 -->|                                              |<-> 21
//     70 ---| GND                                          |<-> 20
//     71 --+| VDD                                          |<-> 19
//     72 ---| GND                  G                   GND |--- 18
//     73 --+| VDD                  N                   VDD |+-- 17
//           |                      D                       |
//           `------^-^-^-^-^-^-^-^---^-^-^-^-^-^-^-^-------'
//                  | | | | | | | | | | | | | | | | |
//                  0 | 2 | 4 | 6 | 8 | 10| 12| 14| 16
//                    1   3   5   7   9   11  13  15


// Z80 has 40 pins in total:
// - 8 bidirectional pins
// - 24 output pins
// - 5 input pins
// - 1 clock (Schmitt trigger)
// - 2 power pins

//                        ,-------.___.-------.
//             <--    A11 |1                40| A10    -->
//             <--    A12 |2                39| A9     -->
//             <--    A13 |3     Z80 CPU    38| A8     -->
//             <--    A14 |4                37| A7     -->
//             <--    A15 |5                36| A6     -->
//             -->    CLK |6                35| A5     -->
//             <->     D4 |7                34| A4     -->
//             <->     D3 |8                33| A3     -->
//             <->     D5 |9                32| A2     -->
//             <->     D6 |10               31| A1     -->
//                +5V VCC |11               30| A0     -->
//             <->     D2 |12               29| GND
//             <->     D7 |13               28| /RFSH  -->
//             <->     D0 |14               27| /M1    -->
//             <->     D1 |15               26| /RESET <--
//             -->   /INT |16               25| /BUSRQ <--
//             -->   /NMI |17               24| /WAIT  <--
//             <--  /HALT |18               23| /BUSAK -->
//             <--  /MREQ |19               22| /WR    -->
//             <--  /IORQ |20               21| /RD    -->
//                        `-------------------'
//

// Z80 pin to wafer.space pad mapping keeping in mind ceramic package:
//
//                    52  50  48  46  44  42  40  38
//                  53| 51| 49| 47  45  43| 41| 39| 37
//                  | | | | | |     |     | | | | | |
//           ,------^-^-^-^-^-^-----------^-^-^-^-^-^-------.
//           |      C A A A A A     g     A A A A A A       |
//     54 <->|D4    L 1 1 1 1 1           1 9 8 7 6 5      v|+-- 36
//     55 <->|D3    K 5 4 3 2 1           0                g|--- 35
//     56 ---|g                                            v|+-- 34
//     57 --+|v                                            g|--- 33
//     58 <->|D5                                          A4|--> 32
//     59 <->|D6                                          A3|--> 31
//     60    |                                            A2|--> 30
//     61    |                      |                     A1|--> 29
//     62 ---|g                   WAFER                   A0|--> 28
//     63 --+|VDD *** Z80 +5V    -SPACE-                    |    27
//     64    |                    GF180      GND Z80 *** GND|--- 26
//     65    |                      |                      v|+-- 25
//     66    |                                              |    24
//     67 <->|D2                                            |    23
//     68 <->|D7                                            |    22
//     69 <->|D0                                            |    21
//     70 ---|g                               B   B R   RFSH|--> 20
//     71 --+|v           H M I               U W U E     M1|--> 19
//     72 ---|g       I N A R O               S A S S      g|--- 18
//     73 --+|v     D N M L E R           R W A I R E      v|+-- 17
//           `.     1 T I T Q Q     d     D R K T Q T       |
//          *  `----^-^-^-v-v-v-----------v-v-v-^-^-^-------'
//                  | | | | | |     |     | | | | | |
//                  v | 2 | 4 | 6   8   10| 12| 14| 16
//                  0 1   3   5   7   9   11  13  15

// out of 56 pads:
// - 1 clock (Schmitt trigger)
// - 8+24 bidir
// - 5 input 
// - 18 unused (forced to input)

module chip_top #(
    // Power/ground pads for core and I/O
    parameter NUM_DVDD_PADS = 8,        // MUST remain unchanged, 8 power pads
    parameter NUM_DVSS_PADS = 10,       // MUST remain unchanged, 10 ground pads

    // Signal pads, 54 (+clock+reset) in total
    parameter NUM_INPUT_PADS = 4+18,    // only 4 necessary for Z80: INT, NMI, WAIT, BUSRQ (not counting clock & reset here)
                                        //      5 for chip configuration
                                        // and the rest (74-8-10-4-8-16-8-2=18) are unused
                                        // unused pins are implemented as input IO cells
    parameter NUM_BIDIR_PADS = 8+16+8   //  8 data bus (bidir) +
                                        //  16 address bus (output) +
                                        //  8 signals (output)
    )(
    `ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
    `endif

    inout  wire clk_PAD,
    inout  wire rst_n_PAD,
    
    inout  wire [NUM_INPUT_PADS-1:0] input_PAD,
    inout  wire [NUM_BIDIR_PADS-1:0] bidir_PAD
);

    wire clk_PAD2CORE;
    wire rst_n_PAD2CORE;
    
    wire [NUM_INPUT_PADS-1:0] input_PAD2CORE;
    wire [NUM_INPUT_PADS-1:0] input_CORE2PAD_PU;
    wire [NUM_INPUT_PADS-1:0] input_CORE2PAD_PD;

    wire [NUM_BIDIR_PADS-1:0] bidir_PAD2CORE;
    wire [NUM_BIDIR_PADS-1:0] bidir_CORE2PAD;
    wire [NUM_BIDIR_PADS-1:0] bidir_CORE2PAD_OE;
    wire [NUM_BIDIR_PADS-1:0] bidir_CORE2PAD_CS;
    wire [NUM_BIDIR_PADS-1:0] bidir_CORE2PAD_SL;
    wire [NUM_BIDIR_PADS-1:0] bidir_CORE2PAD_IE;
    wire [NUM_BIDIR_PADS-1:0] bidir_CORE2PAD_PU;
    wire [NUM_BIDIR_PADS-1:0] bidir_CORE2PAD_PD;

    // Power/ground pad instances
    generate
    for (genvar i=0; i<NUM_DVDD_PADS; i++) begin : dvdd_pads
        (* keep *)
        gf180mcu_ws_io__dvdd pad (
            `ifdef USE_POWER_PINS
            .DVDD   (VDD),
            .DVSS   (VSS),
            .VSS    (VSS)
            `endif
        );
    end
    
    for (genvar i=0; i<NUM_DVSS_PADS; i++) begin : dvss_pads
        (* keep *)
        gf180mcu_ws_io__dvss pad (
            `ifdef USE_POWER_PINS
            .DVDD   (VDD),
            .DVSS   (VSS),
            .VDD    (VDD)
            `endif
        );
    end
    endgenerate

    // Signal IO pad instances

    // Schmitt trigger
    gf180mcu_fd_io__in_s clk_pad (
        `ifdef USE_POWER_PINS
        .DVDD   (VDD),
        .DVSS   (VSS),
        .VDD    (VDD),
        .VSS    (VSS),
        `endif
    
        .Y      (clk_PAD2CORE),
        .PAD    (clk_PAD),
        
        .PU     (1'b0),
        .PD     (1'b0)
    );
    
    // Normal input
    gf180mcu_fd_io__in_c rst_n_pad (
        `ifdef USE_POWER_PINS
        .DVDD   (VDD),
        .DVSS   (VSS),
        .VDD    (VDD),
        .VSS    (VSS),
        `endif
    
        .Y      (rst_n_PAD2CORE),
        .PAD    (rst_n_PAD),
        
        .PU     (1'b0),
        .PD     (1'b0)
    );

    generate
    for (genvar i=0; i<NUM_INPUT_PADS; i++) begin : inputs
        (* keep *)
        gf180mcu_fd_io__in_c pad (
            `ifdef USE_POWER_PINS
            .DVDD   (VDD),
            .DVSS   (VSS),
            .VDD    (VDD),
            .VSS    (VSS),
            `endif
        
            .Y      (input_PAD2CORE[i]),
            .PAD    (input_PAD[i]),
            
            .PU     (input_CORE2PAD_PU[i]),
            .PD     (input_CORE2PAD_PD[i])
        );
    end
    endgenerate

    generate
    for (genvar i=0; i<NUM_BIDIR_PADS; i++) begin : bidir
        (* keep *)
        gf180mcu_fd_io__bi_24t pad (
            `ifdef USE_POWER_PINS
            .DVDD   (VDD),
            .DVSS   (VSS),
            .VDD    (VDD),
            .VSS    (VSS),
            `endif
        
            .A      (bidir_CORE2PAD[i]),
            .OE     (bidir_CORE2PAD_OE[i]),
            .Y      (bidir_PAD2CORE[i]),
            .PAD    (bidir_PAD[i]),
            
            .CS     (bidir_CORE2PAD_CS[i]),
            .SL     (bidir_CORE2PAD_SL[i]),
            .IE     (bidir_CORE2PAD_IE[i]),

            .PU     (bidir_CORE2PAD_PU[i]),
            .PD     (bidir_CORE2PAD_PD[i])
        );
    end
    endgenerate

    // Core design

    chip_core #(
        .NUM_INPUT_PADS  (NUM_INPUT_PADS),
        .NUM_BIDIR_PADS  (NUM_BIDIR_PADS)
    ) i_chip_core (
        `ifdef USE_POWER_PINS
        .VDD        (VDD),
        .VSS        (VSS),
        `endif
    
        .clk        (clk_PAD2CORE),
        .rst_n      (rst_n_PAD2CORE),
    
        .input_in   (input_PAD2CORE),
        .input_pu   (input_CORE2PAD_PU),
        .input_pd   (input_CORE2PAD_PD),

        .bidir_in   (bidir_PAD2CORE),
        .bidir_out  (bidir_CORE2PAD),
        .bidir_oe   (bidir_CORE2PAD_OE),
        .bidir_cs   (bidir_CORE2PAD_CS),
        .bidir_sl   (bidir_CORE2PAD_SL),
        .bidir_ie   (bidir_CORE2PAD_IE),
        .bidir_pu   (bidir_CORE2PAD_PU),
        .bidir_pd   (bidir_CORE2PAD_PD)
    );
    
    // Chip ID - do not remove, necessary for tapeout
    (* keep *)
    gf180mcu_ws_ip__id chip_id ();
    
    // wafer.space logo - can be removed
    (* keep *)
    gf180mcu_ws_ip__logo wafer_space_logo ();

endmodule

`default_nettype wire
