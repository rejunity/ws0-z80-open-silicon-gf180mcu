# SPDX-FileCopyrightText: © 2025 Project Template Contributors
# SPDX-License-Identifier: Apache-2.0

import os
import random
import logging
from pathlib import Path

import cocotb
from cocotb.types import LogicArray
from cocotb.clock import Clock
from cocotb.triggers import Timer, Edge, RisingEdge, FallingEdge, ClockCycles
from cocotb_tools.runner import get_runner

sim = os.getenv("SIM", "icarus")
pdk_root = os.getenv("PDK_ROOT", Path("~/.ciel").expanduser())
pdk = os.getenv("PDK", "gf180mcuD")
scl = os.getenv("SCL", "gf180mcu_fd_sc_mcu9t5v0") # default is: gf180mcu_fd_sc_mcu7t5v0
gl = os.getenv("GL", False)
slot = os.getenv("SLOT", "1x1")

hdl_toplevel = "chip_top"

Z80_FREQ = 4 # in MHz

async def set_defaults(dut):
    dut.input_PAD.value = 0
    dut.bidir_PAD.value = LogicArray('Z' * 24 + '0' * 8)

async def set_inputs(dut, ctrl_in, data_in):
    dut.input_PAD.value = ctrl_in
    if isinstance(data_in, int):
        data_in = f"{data_in:08b}" 
    dut.bidir_PAD.value = LogicArray('Z' * 24 + data_in)

async def enable_power(dut):
    dut.VDD.value = 1
    dut.VSS.value = 0

async def start_clock(clock, freq=50):
    """Start the clock @ freq MHz"""
    c = Clock(clock, 1 / freq * 1000, "ns")
    cocotb.start_soon(c.start())


async def reset(clk, reset, active_low=True, time_ns=1000):
    """Reset dut"""
    cocotb.log.info("Reset asserted...")

    reset.value = not active_low
    await Timer(time_ns, "ns")
    reset.value = active_low

    cocotb.log.info("Reset deasserted.")


async def start_up(dut):
    """Startup sequence"""
    await set_defaults(dut)
    if gl:
        await enable_power(dut)
    await start_clock(dut.clk_PAD, Z80_FREQ)

    await reset(dut.clk_PAD, dut.rst_n_PAD)


CONFIG_EARLY_SIGNALS = 0b10_00_10
BUS_READY = (CONFIG_EARLY_SIGNALS << 4) | 0b1111 # not BUSRQ, not NMI, not INT, not WAIT
BUS_WAIT  = (CONFIG_EARLY_SIGNALS << 4) | 0b1110 # not BUSRQ, not NMI, not INT,     WAIT
BUS_INT   = (CONFIG_EARLY_SIGNALS << 4) | 0b1101 # not BUSRQ, not NMI,     INT, not WAIT
BUS_NMI   = (CONFIG_EARLY_SIGNALS << 4) | 0b1011 # not BUSRQ,     NMI, not INT, not WAIT
BUS_REQ   = (CONFIG_EARLY_SIGNALS << 4) | 0b0111 #     BUSRQ, not NMI, not INT, not WAIT
OPCODE_NOP  = 0x00
OPCODE_LDHL = 0x21
OPCODE_IN   = 0xDB
OPCODE_OUT  = 0xD3
OPCODE_STHL = 0x77
OPCODE_XOR  = 0xAF

@cocotb.test()
async def test__RESET_sequence(dut):
    dut.input_PAD.value = 0
    dut.bidir_PAD.value = LogicArray('Z' * 32)

    dut._log.info("Test RESET")
    if gl:
        await enable_power(dut)
    await start_clock(dut.clk_PAD, Z80_FREQ)

    def print_pins(dut):
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        print (f"{' ' * 84}  pins:{ctrl}|{addr}|{data}")

    cocotb.log.info("Reset asserted...")
    dut.rst_n_PAD.value = False

    await ClockCycles(dut.clk_PAD, 4) # wait at least 3 cycles with RESET asserted according to Z80 Manual
        
    for i in range(8):
        print_pins(dut)
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        assert str(addr) == "Z" * 16    # ADDRESS bus is floating during RESET
        assert str(data) == "Z" * 8     # DATA    bus is floating during RESET
        assert str(ctrl) == "1" * 8     # control signals are deasserted (active low) during RESET
        await ClockCycles(dut.clk_PAD, 1)

    dut.rst_n_PAD.value = True
    cocotb.log.info("Reset deasserted.")

    for i in range(4):
        controls, addr, data = await z80_step(dut, BUS_WAIT, 'Z'*8, i, verbose=False)
        print_pins(dut)
        if i > 0:
            assert controls["m1"] == 1 # M1 is occasionally delayed after RESET cycle (in Gate Level tests)
        assert str(addr) == "0" * 16    # ADDRESS goes to 0 after RESET

    for i in range(4, 16):
        controls, addr, data = await z80_step(dut, BUS_READY, OPCODE_NOP, i, verbose=False)
        print_pins(dut)

@cocotb.test()
async def test__NMI_sequence(dut):
    dut.input_PAD.value = 0
    dut.bidir_PAD.value = LogicArray('Z' * 32)

    dut._log.info("Test NMI")
    if gl:
        await enable_power(dut)
    await start_clock(dut.clk_PAD, Z80_FREQ)

    cocotb.log.info("Reset asserted...")
    dut.rst_n_PAD.value = False
    await ClockCycles(dut.clk_PAD, 16) # wait at least 3 cycles with RESET asserted according to Z80 Manual

    dut.rst_n_PAD.value = True
    cocotb.log.info("Reset deasserted.")

    def print_pins(dut):
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        print (f"{' ' * 84}  pins:{ctrl}|{addr}|{data}")


    z80_cycle = 0
    for i in range(4):
        controls, addr, data = await z80_step(dut, BUS_READY, OPCODE_NOP, z80_cycle, verbose=False)
        print_pins(dut)
        z80_cycle += 1
        if controls["m1"] == 1:
            break

    for int_cycle in range(1, 5):
        reached_nmi_routine = False
        for i in range(64):
            controls, addr, data = await z80_step(dut, (BUS_NMI if i == int_cycle else BUS_READY), OPCODE_NOP, z80_cycle, verbose=True)
            if addr.to_unsigned() == 0x0066:
                reached_nmi_routine = True
                for j in range(4):
                    await z80_step(dut, BUS_READY, OPCODE_NOP, z80_cycle, verbose=True)
                    z80_cycle += 1
                break
            z80_cycle += 1

        assert reached_nmi_routine == True



@cocotb.test()
async def test__INT_sequence(dut):
    dut.input_PAD.value = 0
    dut.bidir_PAD.value = LogicArray('Z' * 32)

    dut._log.info("Test INT")
    if gl:
        await enable_power(dut)
    await start_clock(dut.clk_PAD, Z80_FREQ)

    cocotb.log.info("Reset asserted...")
    dut.rst_n_PAD.value = False
    await ClockCycles(dut.clk_PAD, 16) # wait at least 3 cycles with RESET asserted according to Z80 Manual

    dut.rst_n_PAD.value = True
    cocotb.log.info("Reset deasserted.")

    def print_pins(dut):
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        print (f"{' ' * 84}  pins:{ctrl}|{addr}|{data}")


    z80_cycle = 0
    for i in range(4):
        controls, addr, data = await z80_step(dut, BUS_READY, OPCODE_NOP, z80_cycle, verbose=False)
        print_pins(dut)
        z80_cycle += 1
        if controls["m1"] == 1:
            break

    int_cycle = 5
    cocotb.log.info("Soft interrupts are DISABLES after RESET.")
    for i in range(16):
        controls, addr, data = await z80_step(dut, (BUS_INT if i == int_cycle else BUS_READY), OPCODE_NOP, z80_cycle, verbose=True)
        print_pins(dut)
        if controls["rd"] == 1:
            assert addr.to_unsigned() == z80_cycle // 4 # no software interrupts
        z80_cycle += 1

    cocotb.log.info("Enable soft interrupts.")
    for i in range(4):
        controls, addr, data = await z80_step(dut, BUS_READY, OPCODE_EI, z80_cycle, verbose=True)
        pc = addr.to_unsigned()
        print_pins(dut)
        z80_cycle += 1

    ioreq_set = False
    # reached_int_routine = False
    cocotb.log.info("Enable soft interrupts.")
    for i in range(32):
        controls, addr, data = await z80_step(dut, (BUS_INT if i == int_cycle else BUS_READY), OPCODE_NOP, z80_cycle, verbose=True)
        if controls["ioreq"] == 1:
            ioreq_set = True
        # reached_int_routine = addr.to_unsigned() != z80_cycle // 4
        print_pins(dut)
        z80_cycle += 1

    assert ioreq_set == True
    # assert reached_int_routine == True


@cocotb.test()
async def test__BUSREQ(dut):
    dut.input_PAD.value = 0
    dut.bidir_PAD.value = LogicArray('Z' * 32)

    dut._log.info("Test BUSREQ")
    if gl:
        await enable_power(dut)
    await start_clock(dut.clk_PAD, Z80_FREQ)

    cocotb.log.info("Reset asserted...")
    dut.rst_n_PAD.value = False
    await ClockCycles(dut.clk_PAD, 16) # wait at least 3 cycles with RESET asserted according to Z80 Manual

    dut.rst_n_PAD.value = True
    cocotb.log.info("Reset deasserted.")

    def print_pins(dut):
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        print (f"{' ' * 84}  pins:{ctrl}|{addr}|{data}")


    z80_cycle = 0
    for i in range(4):
        controls, addr, data = await z80_step(dut, BUS_READY, OPCODE_NOP, z80_cycle, verbose=False)
        print_pins(dut)
        z80_cycle += 1
        if controls["m1"] == 1:
            break

    for i in range(9):
        controls, addr, data = await z80_step(dut, BUS_READY, OPCODE_NOP, z80_cycle, verbose=True)
        assert controls["busak"] == 0
        z80_cycle += 1

    last_addr = 0
    last_halt = 0
    for i in range(16):
        controls, addr, data = await z80_step(dut, BUS_REQ, 'Z'*8, z80_cycle, verbose=True)
        if i == 0:
            cocotb.log.info("BUSREQ asserted...")
        if controls["busak"] == 1:
            assert str(addr) == "Z" * 16    # ADDRESS bus is floating during BUSAK
            assert str(data) == "Z" * 8     # DATA    bus is floating during BUSAK
            assert controls["m1"] == 0
            assert controls["rfsh"] == 0
            assert controls["mreq"] == "Z"
            assert controls["rd"] == "Z"
            assert controls["wr"] == "Z"
            assert controls["ioreq"] == "Z"
            assert last_halt == controls["halt"]
            break
        else:
            last_addr = addr.to_unsigned()
            last_halt = controls["halt"]

        z80_cycle += 1

    for i in range(16):
        controls, addr, data = await z80_step(dut, BUS_REQ, 'Z'*8, z80_cycle, verbose=True)
        assert controls["busak"] == 1
        assert str(addr) == "Z" * 16        # ADDRESS bus is floating during BUSAK
        assert str(data) == "Z" * 8         # DATA    bus is floating during BUSAK
        assert controls["m1"] == 0
        assert controls["rfsh"] == 0
        assert controls["mreq"] == "Z"
        assert controls["rd"] == "Z"
        assert controls["wr"] == "Z"
        assert controls["ioreq"] == "Z"
        assert last_halt == controls["halt"]

    for i in range(4):
        controls, addr, data = await z80_step(dut, BUS_READY, OPCODE_NOP, z80_cycle, verbose=True)
        if i == 0:
            cocotb.log.info("BUSREQ deasserted...")
        if controls["busak"] == 0:
            break
        assert i < 2                        # Should take not more than 1 cyle to leave BUSAK state once BUSREQ was deasserted
        assert str(addr) == "Z" * 16        # ADDRESS bus is floating during BUSAK
        assert controls["m1"] == 0
        assert controls["rfsh"] == 0
        assert controls["mreq"] == "Z"
        assert controls["rd"] == "Z"
        assert controls["wr"] == "Z"
        assert controls["ioreq"] == "Z"
        assert last_halt == controls["halt"]

    z80_cycle += 1
    controls, addr, data = await z80_step(dut, BUS_READY, OPCODE_NOP, z80_cycle, verbose=True)
    assert last_addr + 1 == addr.to_unsigned()
    assert controls["busak"] == 0
    assert controls["m1"] == 1
    assert str(addr) != "Z" * 16    # ADDRESS bus is floating during RESET


@cocotb.test()
async def test__timing(dut):
    dut.input_PAD.value = 0
    dut.bidir_PAD.value = LogicArray('Z' * 32)

    dut._log.info("Test TIMING")
    if gl:
        await enable_power(dut)
    await start_clock(dut.clk_PAD, Z80_FREQ)

    def print_pins(dut, edge=True):
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        posneg = '_' if dut.clk_PAD.value == 0 else '^'
        t_ns = str(cocotb.simulator.get_sim_time()[1]//100)
        print (f"clk: {str(dut.clk_PAD.value)} {t_ns} {(posneg if edge else ' ') * 70}  pins:{ctrl}|{addr}|{data}")

    cocotb.log.info("Reset asserted...")
    dut.rst_n_PAD.value = False

    steps_per_cycle = 20
    time_step = 1 / Z80_FREQ * 1000 # "ns"
    time_step = time_step / steps_per_cycle
    print(time_step)
    for i in range(16 * steps_per_cycle):
        await set_inputs(dut, BUS_READY, OPCODE_NOP)
        last_clk = dut.clk_PAD.value
        await Timer(time_step, "ns")
        print_pins(dut, last_clk != dut.clk_PAD.value)

        if i > steps_per_cycle * 4:
            dut.rst_n_PAD.value = True

@cocotb.test()
async def test__FETCH_timing(dut):
    await start_up(dut)
    dut._log.info("Test opcode FETCH timing")


    def print_pins(dut, edge=True):
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        posneg = '_' if dut.clk_PAD.value == 0 else '^'
        t_ns = str(cocotb.simulator.get_sim_time()[1]//100)
        print (f"clk: {str(dut.clk_PAD.value)} {t_ns} {(posneg if edge else ' ') * 70}  pins:{ctrl}|{addr}|{data}")

    def ctrl(dut):
        return convert_control_pins_to_signals(dut.bidir_PAD.value[31:24])
    def addr(dut):
        return dut.bidir_PAD.value[23:8].to_unsigned()

    dut._log.info("Assert WAIT to reach M1|T2 cycle")
    await set_inputs(dut, BUS_WAIT, OPCODE_NOP)
    await ClockCycles(dut.clk_PAD, 4)
    assert ctrl(dut)["m1"]   == 1
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == 0

    # We should be at T2 cycle of M1 now
    dut._log.info("Deassert WAIT")
    await set_inputs(dut, BUS_READY, OPCODE_NOP)
    await ClockCycles(dut.clk_PAD, 1) # T2->T3 
    await ClockCycles(dut.clk_PAD, 1) # T3->T4
    dut._log.info("M1|T4 cycle")

    # NOTE: MREQ might be asserted because of the REFRESH cycle during M1|T4
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["rd"]   == 0
    assert addr(dut) == 0
    await FallingEdge(dut.clk_PAD); print_pins(dut)
    dut._log.info("Middle of M1|T4 cycle")
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["rd"]   == 0
    assert addr(dut) == 0
    await Timer(10, "ns");         print_pins(dut, False)
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["mreq"] == 0
    assert ctrl(dut)["rd"]   == 0
    assert addr(dut) == 0

    dut._log.info("FETCH of the new instruction starts here, leading into M1|T1 cycle")
    await RisingEdge(dut.clk_PAD);  print_pins(dut)                         # _/
    await Timer(100, "ns");         print_pins(dut, False)                  # _/^^ 100 ns
    assert ctrl(dut)["m1"]   == 1                                             
    assert ctrl(dut)["mreq"] == 0
    assert ctrl(dut)["rd"]   == 0
    await Timer( 10, "ns");         print_pins(dut, False)                  # _/^^ 110 ns
    assert addr(dut) == 0x01
    assert ctrl(dut)["mreq"] == 0                                                                           
    await FallingEdge(dut.clk_PAD); print_pins(dut, True)                   # _/^^^\
    assert addr(dut) == 0x01
    assert ctrl(dut)["mreq"] == 0                                                                           # @TODO: guarantee TdA(MREQf) Min 65ns
    await Timer( 85, "ns");         print_pins(dut, False)                  # _/^^^\_ 85ns
    assert ctrl(dut)["m1"]   == 1
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == 0x01

    await RisingEdge(dut.clk_PAD) ; print_pins(dut)                         # _/^^^\___/
    await FallingEdge(dut.clk_PAD); print_pins(dut)                         # _/^^^\___/^^^\
    assert ctrl(dut)["m1"]   == 1
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == 0x01

    await Timer(125-35, "ns");      print_pins(dut, False)                  # _/^^^\__ -35ns_/
    dut._log.info("DATA is expected to settle, leading into M1|T3")
    assert ctrl(dut)["m1"]   == 1
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == 0x01

    await RisingEdge(dut.clk_PAD);  print_pins(dut)                         # _/^^^\___/^^^\___/
    await Timer(100, "ns");         print_pins(dut, False)                  # _/^^^\___/^^^\___/^^ 100 ns
    assert ctrl(dut)["mreq"] == 0
    assert ctrl(dut)["rd"]   == 0
    assert addr(dut) == 0x01
    await Timer( 10, "ns");         print_pins(dut, False)                  # _/^^^\___/^^^\___/^^ 110 ns
    assert ctrl(dut)["m1"]   == 0
    assert addr(dut) == 0x01

@cocotb.test()
async def test__READ_timing(dut):
    await start_up(dut)
    dut._log.info("Test memory READ timing")


    def print_pins(dut, edge=True):
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        posneg = '_' if dut.clk_PAD.value == 0 else '^'
        t_ns = str(cocotb.simulator.get_sim_time()[1]//100)
        print (f"clk: {str(dut.clk_PAD.value)} {t_ns} {(posneg if edge else ' ') * 70}  pins:{ctrl}|{addr}|{data}")

    def ctrl(dut):
        return convert_control_pins_to_signals(dut.bidir_PAD.value[31:24])
    def addr(dut):
        return dut.bidir_PAD.value[23:8].to_unsigned()

    dut._log.info("Assert WAIT to reach M1|T2 cycle")
    await set_inputs(dut, BUS_WAIT, OPCODE_LDHL)
    await ClockCycles(dut.clk_PAD, 4)
    assert ctrl(dut)["m1"]   == 1
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == 0

    # We should be at T2 cycle of M1 now
    dut._log.info("Deassert WAIT")
    await set_inputs(dut, BUS_READY, OPCODE_LDHL)
    await ClockCycles(dut.clk_PAD, 1) # T2->T3 
    await ClockCycles(dut.clk_PAD, 1) # T3->T4
    dut._log.info("M1|T4 cycle")

    # NOTE: MREQ might be asserted because of the REFRESH cycle during M1|T4
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["rd"]   == 0
    assert addr(dut) == 0
    await FallingEdge(dut.clk_PAD); print_pins(dut)
    dut._log.info("Middle of M1|T4 cycle")
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["rd"]   == 0
    assert addr(dut) == 0
    await Timer(10, "ns");         print_pins(dut, False)
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["mreq"] == 0
    assert ctrl(dut)["rd"]   == 0
    assert addr(dut) == 0

    dut._log.info("FETCH of the new instruction starts here, leading into M2|T1 cycle")
    # await RisingEdge(dut.clk_PAD);  print_pins(dut)                 # _/
    # await Timer(100, "ns");         print_pins(dut, False)          # _/^^ 100 ns
    # assert ctrl(dut)["m1"]   == 1                                     
    # assert ctrl(dut)["mreq"] == 0
    # assert ctrl(dut)["rd"]   == 0
    # await Timer( 10, "ns");         print_pins(dut, False)          # _/^^ 110 ns
    # assert addr(dut) == 0x01
    # assert ctrl(dut)["mreq"] == 0                                                                   
    # await FallingEdge(dut.clk_PAD); print_pins(dut, True)           # _/^^^\
    # assert addr(dut) == 0x01
    # assert ctrl(dut)["mreq"] == 0                                   # @TODO: guarantee TdA(MREQf) Min 65ns
    # await Timer( 85, "ns");         print_pins(dut, False)          # _/^^^\_ 85ns
    # assert ctrl(dut)["m1"]   == 1
    # assert ctrl(dut)["mreq"] == 1
    # assert ctrl(dut)["rd"]   == 1
    # assert addr(dut) == 0x01

    # await RisingEdge(dut.clk_PAD) ; print_pins(dut)                 # _/^^^\___/
    # await FallingEdge(dut.clk_PAD); print_pins(dut)                 # _/^^^\___/^^^\
    # assert ctrl(dut)["m1"]   == 1
    # assert ctrl(dut)["mreq"] == 1
    # assert ctrl(dut)["rd"]   == 1
    # assert addr(dut) == 0x01

    # await Timer(125-35, "ns");      print_pins(dut, False)          # _/^^^\___/^^^\__ -35ns_/
    # dut._log.info("DATA is expected to settle, leading into M1|T3")
    # assert ctrl(dut)["m1"]   == 1
    # assert ctrl(dut)["mreq"] == 1
    # assert ctrl(dut)["rd"]   == 1
    # assert addr(dut) == 0x01

    # await RisingEdge(dut.clk_PAD);  print_pins(dut)                 # _/^^^\___/^^^\___/
    # await Timer(100, "ns");         print_pins(dut, False)          # _/^^^\___/^^^\___/^^ 100 ns
    # assert ctrl(dut)["mreq"] == 0
    # assert ctrl(dut)["rd"]   == 0
    # assert addr(dut) == 0x01
    # await Timer( 10, "ns");         print_pins(dut, False)          # _/^^^\___/^^^\___/^^ 110 ns
    # assert ctrl(dut)["m1"]   == 0
    # assert addr(dut) == 0x01


    # await FallingEdge(dut.clk_PAD); print_pins(dut)                 # _/^^^\___/^^^\___/^^^\
    # await RisingEdge(dut.clk_PAD) ; print_pins(dut)                 # _/^^^\___/^^^\___/^^^\___/
    # await FallingEdge(dut.clk_PAD); print_pins(dut)                 # _/^^^\___/^^^\___/^^^\___/^^^\

    dut._log.info("READ from memory starts here, leading into M2|T1")
    await RisingEdge(dut.clk_PAD);  print_pins(dut)                 # ... _/
    await Timer(100, "ns");         print_pins(dut, False)          # ... _/^^ 100 ns
    assert ctrl(dut)["m1"]   == 0                                     
    assert ctrl(dut)["mreq"] == 0
    assert ctrl(dut)["rd"]   == 0
    await Timer( 10, "ns");         print_pins(dut, False)          # ... _/^^ 110 ns
    assert addr(dut) == 0x01
    assert ctrl(dut)["mreq"] == 0     
    await FallingEdge(dut.clk_PAD); print_pins(dut, True)           # ... _/^^^\
    assert addr(dut) == 0x01
    assert ctrl(dut)["mreq"] == 0                                   # @TODO: guarantee TdA(MREQf) Min 65ns
    await Timer( 85, "ns");         print_pins(dut, False)          # ... _/^^^\_ 85ns
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == 0x01


    await RisingEdge(dut.clk_PAD) ; print_pins(dut)                 # ... _/^^^\___/
    await FallingEdge(dut.clk_PAD); print_pins(dut)                 # ... _/^^^\___/^^^\
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == 0x01

    await Timer(125-50, "ns");      print_pins(dut, False)          # ... _/^^^\___/^^^\__ -50ns_/
    dut._log.info("DATA is expected to settle, leading into M2|T3")
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == 0x01

    await RisingEdge(dut.clk_PAD);  print_pins(dut)                 # ... _/^^^\___/^^^\___/
    await Timer(100, "ns");         print_pins(dut, False)          # ... _/^^^\___/^^^\___/^^ 100 ns
    assert ctrl(dut)["mreq"] == 0
    assert ctrl(dut)["rd"]   == 0
    assert addr(dut) == 0x01
    await Timer( 10, "ns");         print_pins(dut, False)          # ... _/^^^\___/^^^\___/^^ 110 ns
    assert ctrl(dut)["m1"]   == 0
    assert addr(dut) == 0x01                                        # @TODO: guarantee TdCTr(A) Min 80ns


@cocotb.test()
async def test__WRITE_timing(dut):
    await start_up(dut)
    dut._log.info("Test memory WRITE timing")


    def print_pins(dut, edge=True):
        data = dut.bidir_PAD.value[7:0]
        addr = dut.bidir_PAD.value[23:8]
        ctrl = dut.bidir_PAD.value[31:24]
        posneg = '_' if dut.clk_PAD.value == 0 else '^'
        t_ns = str(cocotb.simulator.get_sim_time()[1]//100)
        print (f"clk: {str(dut.clk_PAD.value)} {t_ns} {(posneg if edge else ' ') * 70}  pins:{ctrl}|{addr}|{data}")

    def ctrl(dut):
        return convert_control_pins_to_signals(dut.bidir_PAD.value[31:24])
    def addr(dut):
        return dut.bidir_PAD.value[23:8].to_unsigned()
    def data(dut):
        return dut.bidir_PAD.value[7:0]

    pc = 0
    dut._log.info("XOR A")
    await set_inputs(dut, BUS_WAIT, OPCODE_XOR)
    await ClockCycles(dut.clk_PAD, 4)
    await set_inputs(dut, BUS_READY, OPCODE_XOR)
    await ClockCycles(dut.clk_PAD, 2)
    pc = pc + 1
    dut._log.info("LD HL, $2121")
    await set_inputs(dut, BUS_READY, OPCODE_LDHL)
    await ClockCycles(dut.clk_PAD, 10)
    pc = pc + 3

    dut._log.info("Assert WAIT to reach M1|T2 cycle")
    await set_inputs(dut, BUS_WAIT, OPCODE_STHL)
    await ClockCycles(dut.clk_PAD, 4)
    assert ctrl(dut)["m1"]   == 1
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 1
    assert addr(dut) == pc

    # We should be at T2 cycle of M1 now
    dut._log.info("Deassert WAIT")
    await set_inputs(dut, BUS_READY, OPCODE_STHL)
    await ClockCycles(dut.clk_PAD, 1) # T2->T3
    await ClockCycles(dut.clk_PAD, 1) # T3->T4
    dut._log.info("M1|T4 cycle")

    await set_inputs(dut, BUS_READY, 'Z'*8)
    dut._log.info("WRITE to memory starts here, leading into M3|T1")
    await RisingEdge(dut.clk_PAD);  print_pins(dut)                 # ... _/
    await Timer(100, "ns");         print_pins(dut, False)          # ... _/^^ 100 ns
    assert ctrl(dut)["m1"]   == 0                                     
    assert ctrl(dut)["mreq"] == 0
    assert ctrl(dut)["rd"]   == 0
    assert ctrl(dut)["wr"]   == 0
    await Timer( 10, "ns");         print_pins(dut, False)          # ... _/^^ 110 ns
    assert addr(dut) == 0x2121
    assert ctrl(dut)["mreq"] == 0     
    await FallingEdge(dut.clk_PAD); print_pins(dut, True)           # ... _/^^^\
    assert addr(dut) == 0x2121
    assert ctrl(dut)["mreq"] == 0                                   # @TODO: guarantee TdA(MREQf) Min 65ns
    await Timer( 85, "ns");         print_pins(dut, False)          # ... _/^^^\_ 85ns
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["rd"]   == 0
    assert ctrl(dut)["wr"]   == 0
    assert addr(dut) == 0x2121

    # await Timer(150-85, "ns");      print_pins(dut, False)          # ... _/^^^\_ 150ns
    # assert ctrl(dut)["m1"]   == 0
    # assert ctrl(dut)["mreq"] == 1
    # assert ctrl(dut)["rd"]   == 0
    # assert ctrl(dut)["wr"]   == 0
    # assert addr(dut) == 0x02
    # assert data(dut) == 0x00 # will fail

    # await Timer(150+80-85, "ns");   print_pins(dut, False)          # ... _/^^^\_ 150ns + 80ns
    # assert ctrl(dut)["m1"]   == 0
    # assert ctrl(dut)["mreq"] == 1
    # assert ctrl(dut)["rd"]   == 0
    # assert ctrl(dut)["wr"]   == 0
    # assert addr(dut) == 0x02
    # assert data(dut) == 0x00 # will fail

    # @TODO: guarantee TdCf(D)    Max 150ns - "Clock Fall to Data Valid delay"
    # @TODO: guarantee TdD(WRf)Mw Min 80ns  - "Data stable prior to /WR Fall"
    # @TODO: guarantee TwWR       Min 220ns - "/WR pulse width"
    # @TODO: guarantee TdWRr(D)   Min 60ns  - "Data stable from /WR Rise"

    await RisingEdge(dut.clk_PAD) ; print_pins(dut)                 # ... _/^^^\___/
    await FallingEdge(dut.clk_PAD); print_pins(dut)                 # ... _/^^^\___/^^^\
    await Timer(80, "ns");          print_pins(dut, False)          # ... _/^^^\___/^^^\_ 80ns
    assert ctrl(dut)["m1"]   == 0
    assert ctrl(dut)["mreq"] == 1
    assert ctrl(dut)["wr"]   == 1
    assert ctrl(dut)["rd"]   == 0
    assert data(dut) == '0'*8
    assert addr(dut) == 0x2121


    await RisingEdge(dut.clk_PAD);  print_pins(dut)                 # ... _/^^^\___/^^^\___/
    await Timer(85, "ns");          print_pins(dut, False)          # ... _/^^^\___/^^^\___/^^ 85 ns
    assert ctrl(dut)["mreq"] == 0
    assert ctrl(dut)["wr"]   == 0
    assert addr(dut) == 0x2121
    await Timer( 10, "ns");         print_pins(dut, False)          # ... _/^^^\___/^^^\___/^^ 95 ns
    assert ctrl(dut)["m1"]   == 0
    assert addr(dut) == 0x2121                                      # @TODO: guarantee TdCTr(A) Min 80ns


@cocotb.test()
async def test__NOP(dut):
    await start_up(dut)
    dut._log.info("Test NOP")

    opcode = OPCODE_NOP
    cycles_per_instr = 4
    
    z80_cycle = 1
    for i in range(4): await z80_step(dut, BUS_WAIT, opcode)
    for i in range(32):
        controls, addr, data = await z80_step(dut, BUS_READY, opcode, z80_cycle, verbose=True)

        if z80_cycle % cycles_per_instr == 0 or \
           z80_cycle % cycles_per_instr == 1:
            assert controls['m1'] == 1
        if z80_cycle % cycles_per_instr == 1:
            assert controls['mreq'] == 1
            assert controls['rd'] == 1
        assert controls['wr'] == 0
        assert controls['ioreq'] == 0
        assert controls['halt'] == 0
        assert controls['busak'] == 0
        if z80_cycle < cycles_per_instr-1:
            assert addr == z80_cycle // 4 # Running NOPs, every 4 cycles address increases
        z80_cycle += 1

@cocotb.test()
async def test__LD_HLx2121(dut):
    await start_up(dut)
    dut._log.info("Test LD HL, $2121")

    opcode = OPCODE_LDHL
    cycles_per_instr = 10

    z80_cycle = 1
    for i in range(4): await z80_step(dut, BUS_WAIT, opcode)
    for i in range(32):
        controls, addr, data = await z80_step(dut, BUS_READY, opcode, z80_cycle, verbose=True)

        if z80_cycle % cycles_per_instr == 0 or \
           z80_cycle % cycles_per_instr == 1:
            assert controls['m1'] == 1
        if z80_cycle % cycles_per_instr == 1 or \
           z80_cycle % cycles_per_instr == 5 or \
           z80_cycle % cycles_per_instr == 8:
            assert controls['mreq'] == 1
            assert controls['rd'] == 1
        assert controls['wr'] == 0
        assert controls['ioreq'] == 0
        assert controls['halt'] == 0
        assert controls['busak'] == 0
        z80_cycle += 1


@cocotb.test()
async def test__LD_INxDB(dut):
    await start_up(dut)
    dut._log.info("Test IN A, ($DB)")

    opcode = OPCODE_IN
    cycles_per_instr = 11

    z80_cycle = 1
    for i in range(4): await z80_step(dut, BUS_WAIT, opcode)
    for i in range(32):
        controls, addr, data = await z80_step(dut, BUS_READY, opcode, z80_cycle, verbose=True)

        if z80_cycle % cycles_per_instr == 0 or \
           z80_cycle % cycles_per_instr == 1:
            assert controls['m1'] == 1
        if z80_cycle % cycles_per_instr == 1 or \
           z80_cycle % cycles_per_instr == 5:
            assert controls['mreq'] == 1
            assert controls['rd'] == 1
            assert controls['ioreq'] == 0
        if z80_cycle % cycles_per_instr == 8 or \
           z80_cycle % cycles_per_instr == 9:
            assert controls['ioreq'] == 1
            assert controls['mreq'] == 0
            assert addr.to_unsigned() & 0xFF == 0xDB
        assert controls['wr'] == 0
        assert controls['halt'] == 0
        assert controls['busak'] == 0
        z80_cycle += 1

@cocotb.test()
async def test__LD_OUTxD3(dut):
    await start_up(dut)
    dut._log.info("Test OUT ($D3), A")

    opcode = OPCODE_OUT
    cycles_per_instr = 11

    z80_cycle = 1
    for i in range(4): await z80_step(dut, BUS_READY, OPCODE_XOR)
    for i in range(4): await z80_step(dut, BUS_WAIT, opcode)
    for i in range(32):
        data = opcode if ((z80_cycle % cycles_per_instr) > 0) and ((z80_cycle % cycles_per_instr) < 6) else 'Z' * 8
        controls, addr, data = await z80_step(dut, BUS_READY, data, z80_cycle, verbose=True)

        if z80_cycle % cycles_per_instr == 0 or \
           z80_cycle % cycles_per_instr == 1:
            assert controls['m1'] == 1
        if z80_cycle % cycles_per_instr == 1 or \
           z80_cycle % cycles_per_instr == 5:
            assert controls['mreq'] == 1
            assert controls['rd'] == 1
            assert controls['ioreq'] == 0
            assert controls['wr'] == 0
        if z80_cycle % cycles_per_instr == 8 or \
           z80_cycle % cycles_per_instr == 9:
            assert controls['ioreq'] == 1
            assert controls['wr'] == 1
            assert controls['mreq'] == 0
            assert controls['rd'] == 0
            assert addr.to_unsigned() & 0xFF == 0xD3
        assert controls['halt'] == 0
        assert controls['busak'] == 0
        z80_cycle += 1

@cocotb.test()
async def test__LD_ptrHL_A(dut):
    await start_up(dut)
    dut._log.info("Test LD (HL), A")

    opcode = OPCODE_STHL
    cycles_per_instr = 7

    z80_cycle = 1
    for i in range(4): await z80_step(dut, BUS_READY, OPCODE_XOR)
    for i in range(4): await z80_step(dut, BUS_WAIT, opcode)
    for i in range(32):
        data = opcode if ((z80_cycle % cycles_per_instr) > 0) and ((z80_cycle % cycles_per_instr) < 3) else 'Z' * 8
        controls, addr, data = await z80_step(dut, BUS_READY, data, z80_cycle, verbose=True)

        if z80_cycle % cycles_per_instr == 0 or \
           z80_cycle % cycles_per_instr == 1:
            assert controls['m1'] == 1
        if z80_cycle % cycles_per_instr == 1:
            assert controls['mreq'] == 1
            assert controls['rd'] == 1
            assert controls['wr'] == 0
        if z80_cycle % cycles_per_instr == 5:
            assert controls['mreq'] == 1
            assert controls['wr'] == 1
            assert controls['rd'] == 0
        assert controls['halt'] == 0
        assert controls['busak'] == 0
        z80_cycle += 1
               
async def z80_step(z80, ctrl_in, data_in, cycle=-1, verbose=False):
    await set_inputs(z80, ctrl_in, data_in)
    await ClockCycles(z80.clk_PAD, 1)
    data = z80.bidir_PAD.value[7:0]
    addr = z80.bidir_PAD.value[23:8]
    cpin = z80.bidir_PAD.value[31:24]

    ctrl = convert_control_pins_to_signals(cpin)

    if (verbose):
        hex_addr = f"0x{addr.to_unsigned():04X}" if addr.is_resolvable else "xx----"
        print (f"clk: {cycle:3d}  {ctrl}  addr:{hex_addr}    pins:{cpin}|{addr}|{data}" \
            .replace("'", "").replace("{", "").replace("}", "").replace(",", ""))
        m1 = ctrl['m1']==True
        rd = ctrl['rd']==True
        wr = ctrl['wr']==True
        if m1 and rd:
            print(f"    OPCODE: {data_in}")
        elif rd:
            print(f"    READ DATA: {data}")
        if wr:
            print(f"    WRITE DATA: {data_in}")
    return ctrl, addr, data

def convert_control_pins_to_signals(ctrl):
    # def is_bit_active_low(byte, n):
    #     return byte & (1<<n) == 0
    def is_bit_active_low(logic_array, n):
        return str(logic_array)[-n-1] == "0"
    def is_bit_floating(logic_array, n):
        return str(logic_array)[-n-1] == "Z"

    ctrl = ['Z' if is_bit_floating(ctrl, n) else int(is_bit_active_low(ctrl, n)) for n in range(8)]
    ctrl = dict(zip(['m1', 'mreq', 'ioreq', 'rd', 'wr', 'rfsh', 'halt', 'busak'], ctrl))
    return ctrl

# EXAMPLE: the following code is example from the original template
# @cocotb.test()
# async def test_counter(dut):
#     """Run the counter test"""

#     # Create a logger for this testbench
#     logger = logging.getLogger("my_testbench")

#     logger.info("Startup sequence...")

#     # Start up
#     await start_up(dut)

#     logger.info("Running the test...")

#     # Wait for some time...
#     await ClockCycles(dut.clk_PAD, 10)

#     # Start the counter by setting all inputs to 1
#     dut.input_PAD.value = -1

#     # Wait for a number of clock cycles
#     await ClockCycles(dut.clk_PAD, 100)

#     # Check the end result of the counter
#     assert dut.bidir_PAD.value == 100 - 1

#     logger.info("Done!")


def chip_top_runner():

    proj_path = Path(__file__).resolve().parent

    sources = []
    defines = {f"SLOT_{slot.upper()}": True}
    includes = [proj_path / "../src/"]

    if gl:
        # SCL models
        sources.append(Path(pdk_root) / pdk / "libs.ref" / scl / "verilog" / f"{scl}.v")
        sources.append(Path(pdk_root) / pdk / "libs.ref" / scl / "verilog" / "primitives.v")

        # We use the powered netlist
        sources.append(proj_path / f"../final/pnl/{hdl_toplevel}.pnl.v")

        defines = {"FUNCTIONAL": True, "USE_POWER_PINS": True}
    else:
        # @TODO: parse and extract *.sv, *.v files from config.yaml
        sources.append(proj_path / "../src/chip_top.sv")
        sources.append(proj_path / "../src/chip_core.sv")
        sources.append(proj_path / "../src/ws_z80.v")
        sources.append(proj_path / "../src/tv80s.v")
        sources.append(proj_path / "../src/tv80_alu.v")
        sources.append(proj_path / "../src/tv80_core.v")
        sources.append(proj_path / "../src/tv80_mcode.v")
        sources.append(proj_path / "../src/tv80_reg.v")

    sources += [
        # IO pad models
        Path(pdk_root) / pdk / "libs.ref/gf180mcu_fd_io/verilog/gf180mcu_fd_io.v",
        Path(pdk_root) / pdk / "libs.ref/gf180mcu_fd_io/verilog/gf180mcu_ws_io.v",
        
        # SRAM macros
        Path(pdk_root) / pdk / "libs.ref/gf180mcu_fd_ip_sram/verilog/gf180mcu_fd_ip_sram__sram512x8m8wm1.v",
        
        # Custom IP
        proj_path / "../ip/gf180mcu_ws_ip__id/vh/gf180mcu_ws_ip__id.v",
        proj_path / "../ip/gf180mcu_ws_ip__logo/vh/gf180mcu_ws_ip__logo.v",
    ]

    build_args = []

    if sim == "icarus":
        # For debugging
        # build_args = ["-Winfloop", "-pfileline=1"]
        pass

    if sim == "verilator":
        build_args = ["--timing", "--trace", "--trace-fst", "--trace-structs"]

    runner = get_runner(sim)
    runner.build(
        sources=sources,
        hdl_toplevel=hdl_toplevel,
        defines=defines,
        always=True,
        includes=includes,
        build_args=build_args,
        waves=True,
    )

    plusargs = []

    runner.test(
        hdl_toplevel=hdl_toplevel,
        test_module="chip_top_tb,",
        plusargs=plusargs,
        waves=True,
    )


if __name__ == "__main__":
    chip_top_runner()
