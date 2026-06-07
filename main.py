# main.py
# ---------------------------------------------------------------------------
# Breadboard PCB tester (Raspberry Pi Pico, MicroPython) for three boards that
# share the same 10-pin header. All ten header pins are wired to GP0..GP9
# (DUT pin i -> GP(i-1)); NO hard ground is used, so VCC/GND for each board
# are synthesised by driving the matching GPIO high/low. One wiring, three boards.
#
#   (1) 3x open-collector NAND
#       header: 1:A 2:B 3:~(A&B) 4:C 5:D 6:~(C&D) 7:E 8:F 9:~(E&F) 10:GND
#       Drive the 6 inputs, read the 3 open-collector outputs (Pico pull-ups),
#       GND synthesised on GP9.
#
#   (2) 2x RS flip-flop (cross-coupled latch; each R/S is an open node pulled
#       up to VCC on the board, and is BOTH driven and read)
#       header: 1:VCC 2:R1 3:NC 4:S1 5:NC 6:GND 7:NC 8:R2 9:NC 10:S2
#       VCC=GP0 high, GND=GP5 low. To flip a latch, sink one node low then
#       release; the node stays low and its partner goes high, and it holds.
#
#   (3) 2x XNOR
#       header: 1:A 2:A~^B 3:B 4:NC 5:GND 6:VCC 7:NC 8:C 9:C~^D 10:D
#       VCC=GP5 high, GND=GP4 low. Drive each gate's two inputs, read the
#       output (= 1 iff the inputs are equal).
#
# Auto-detection: run the NAND test; if a gate works it's NAND. Else the RS test;
# if a flip-flop works it's RS. Else fall back to XNOR (shown regardless). Set
# BOARD below to force one type and skip detection.
#
# Optional NAND transistor-orientation check (ORIENT_CHECK, needs an ADC wire +
# load resistor) measures a gate's output voltage under load to flag reversed
# (collector/emitter-swapped) transistors, which still pass the truth table.
#
# Output: SBC-OLED01 (SSD1306) with page rotation, onboard LED, USB serial.
# Needs ssd1306.py on the Pico too (optional; falls back to serial + LED).
# ---------------------------------------------------------------------------

from machine import Pin, I2C, ADC
import time

# ====== board selection ======
BOARD = "auto"           # "auto" (NAND, then RS, then XNOR), "nand", "rs", "xnor"

# ====== DUT header wiring: DUT pin i (1..10) -> GP(i-1) ======
PINS = [Pin(g, Pin.IN) for g in range(10)]   # index == DUT pin - 1 == GP number


def drive(gp, level):
    PINS[gp].init(Pin.OUT)
    PINS[gp].value(level)


def release(gp, pull=None):
    if pull is None:
        PINS[gp].init(Pin.IN)
    else:
        PINS[gp].init(Pin.IN, pull)


def read(gp):
    return PINS[gp].value()


SETTLE_US = 300


def read_stable(gp, samples=5):
    """Majority-vote a few samples to reject the occasional glitch."""
    s = 0
    for _ in range(samples):
        s += read(gp)
        time.sleep_us(50)
    return 1 if s * 2 > samples else 0


led = Pin("LED", Pin.OUT)

# ====== OLED status display (SSD1306, 128x64, I2C1 on GP26/GP27) ======
OLED_W, OLED_H = 128, 64
PAGE_MS = 3500           # ms a summary/overview page is shown before rotating
DETAIL_MS = 8000         # ms a failure-detail page is shown (more to read)
oled = None
try:
    from ssd1306 import SSD1306_I2C
    _i2c = I2C(1, sda=Pin(26), scl=Pin(27), freq=400_000)
    oled = SSD1306_I2C(OLED_W, OLED_H, _i2c, addr=0x3C)
except Exception as exc:                       # noqa: BLE001 - any I2C/import error
    print("OLED unavailable (%s); serial + LED only" % exc)


def render_lines(lines, invert=0):
    if oled is None:
        return
    oled.invert(invert)
    oled.fill(0)
    y = 0
    for ln in lines[:7]:
        oled.text(ln, 0, y)
        y += 9
    oled.show()


# ====== board 1: 3x open-collector NAND ======
NAND_GATES = [("G1 ~(A&B)", 0, 1, 2),          # (name, A_gp, B_gp, Y_gp)
              ("G2 ~(C&D)", 3, 4, 5),
              ("G3 ~(E&F)", 6, 7, 8)]
NAND_DRIVE = [0, 1, 3, 4, 6, 7]
NAND_GND = 9


def nand_test():
    drive(NAND_GND, 0)                          # synthesise GND on the pin-10 line
    for _, _, _, y in NAND_GATES:
        release(y, Pin.PULL_UP)                 # open-collector outputs need a pull-up
    for gp in NAND_DRIVE:
        drive(gp, 0)
    results = []
    for name, a_gp, b_gp, y_gp in NAND_GATES:
        ok = True
        rows = []
        for a in (0, 1):
            for b in (0, 1):
                for gp in NAND_DRIVE:
                    drive(gp, 0)
                drive(a_gp, a)
                drive(b_gp, b)
                time.sleep_us(SETTLE_US)
                got = read_stable(y_gp)
                exp = 0 if (a and b) else 1     # NAND
                passed = (got == exp)
                ok = ok and passed
                rows.append((a, b, exp, got, passed))
        results.append((name, ok, rows))
    return results


def nand_pages(results, all_ok, vol_info=None):
    summary = ["3x NAND TESTER"]
    for name, ok, _ in results:
        summary.append("%s %s" % (name, "PASS" if ok else "FAIL"))
    if vol_info:                                 # show V_OL right on the summary
        gname, vol, _fwd = vol_info
        summary.append("%s VOL=%.2fV" % (gname.split()[0], vol))
    else:
        summary.append("")
    summary.append("ALL GATES PASS" if all_ok else "** FAULT **")
    pages = [(summary, 0 if all_ok else 1, PAGE_MS)]
    for name, ok, rows in results:
        if not ok:
            lines = ["%s FAIL" % name, "ab exp got"]
            for a, b, exp, got, p in rows:
                lines.append("%d%d  %d   %d  %s" % (a, b, exp, got, "ok" if p else "BAD"))
            pages.append((lines, 0, DETAIL_MS))
    return pages


def print_nand(results, all_ok):
    print("Board: 3x open-collector NAND")
    for name, ok, rows in results:
        print("  %-11s %s" % (name, "PASS" if ok else "FAIL"))
        for a, b, exp, got, p in rows:
            print("     a=%d b=%d exp=%d got=%d %s"
                  % (a, b, exp, got, "ok" if p else "<- MISMATCH"))
    print("  RESULT:", "ALL GATES PASS" if all_ok else "FAULT DETECTED")


# ====== optional: NAND transistor-orientation check (V_OL under load) ======
# A correctly-built open-collector NAND sinks current through a high-beta FORWARD
# transistor, so its output stays near 0 V even under load. If the two stacked
# transistors are wired collector<->emitter swapped, they still pass the truth
# table (saturation conducts both ways) but sink WEAKLY (low reverse beta), so
# the output sags high under load. We expose that by loading one gate's output
# and reading its low-level voltage (V_OL) on the ADC.
#
# Extra hardware (see README "Transistor-orientation check"), then set
# ORIENT_CHECK = True (and remove the wires + set it back to False afterwards,
# since the ADC jumper / load resistor get in the way of the RS-flip-flop board):
#   - jumper the chosen gate's OUTPUT to GP28  (ADC2, physical pin 34)
#   - ~1 kOhm resistor from that OUTPUT to GP22 (physical pin 29); GP22 is the
#     switchable load driver, so the normal NAND test is left untouched.
ORIENT_CHECK = False        # True only when the ADC wire + load resistor are fitted
ORIENT_GATE = 0              # 0=G1 (out GP2), 1=G2 (out GP5), 2=G3 (out GP8)
ORIENT_ADC_GP = 28          # GP28 = ADC2; jumper the gate output here
ORIENT_LOAD_GP = 22         # GP22 -> ~1k -> gate output (load, on only during test)
ORIENT_THRESH_V = 1.2       # V_OL above this = weak sink = likely reversed
ADC_VREF = 3.3              # measured refs: forward ~0.20 V, reversed ~2.35 V


# GP22 (load) and GP28 (ADC) live outside the DUT range GP0..GP9, so they get
# their own objects (created lazily on first use) rather than going through
# PINS[]/drive()/release().
_orient_load = None
_orient_adc = None


def orient_test():
    global _orient_load, _orient_adc
    if _orient_load is None:
        _orient_load = Pin(ORIENT_LOAD_GP, Pin.IN)   # start Hi-Z (load off)
        _orient_adc = ADC(Pin(ORIENT_ADC_GP))
    name, a_gp, b_gp, y_gp = NAND_GATES[ORIENT_GATE]
    drive(NAND_GND, 0)                       # power the gate as usual (GND low)
    for gp in NAND_DRIVE:
        drive(gp, 0)
    release(y_gp)                            # output sensed by the ADC, not pulled here
    drive(a_gp, 1)                           # A=B=high -> a good gate pulls output LOW
    drive(b_gp, 1)
    _orient_load.init(Pin.OUT)               # apply the ~1k load toward 3.3 V
    _orient_load.value(1)
    time.sleep_ms(3)
    acc = 0
    for _ in range(16):
        acc += _orient_adc.read_u16()
        time.sleep_us(200)
    vol = (acc / 16) / 65535 * ADC_VREF
    _orient_load.init(Pin.IN)                # remove the load (Hi-Z) when done
    return name, vol, (vol < ORIENT_THRESH_V)


def orient_page(name, vol, forward):
    return ([
        "ORIENT %s" % name,
        "V_OL=%.2f V" % vol,
        "under ~1k load",
        "",
        "-> FORWARD ok" if forward else "-> REVERSED?",
    ], 0 if forward else 1, DETAIL_MS)


# ====== board 2: 2x RS flip-flop ======
RS_FFS = [("FF1", 1, 3), ("FF2", 7, 9)]        # (name, R_gp, S_gp)
RS_VCC = 0
RS_GND = 5
RS_NC = [2, 4, 6, 8]
RS_CYCLES = 4


def rs_setup():
    drive(RS_VCC, 1)         # VCC = logic high (board needs very little power)
    drive(RS_GND, 0)         # GND = logic low
    for gp in RS_NC:
        release(gp)
    for _, r, s in RS_FFS:
        release(r)           # both nodes high-Z; board pull-ups define the highs
        release(s)
    time.sleep_ms(3)


def rs_pulse_low(gp):
    drive(gp, 0)             # sink the node to ground to flip the latch
    time.sleep_us(SETTLE_US)
    release(gp)              # back to high-Z so the latch holds and we can read
    time.sleep_us(SETTLE_US)


def rs_test():
    rs_setup()
    results = []
    for name, r, s in RS_FFS:
        ok = True
        fail_obs = None
        r1 = s1 = r2 = s2 = -1
        for cyc in range(RS_CYCLES):
            rs_pulse_low(r)                              # RESET -> expect R=0 S=1
            r1, s1 = read_stable(r), read_stable(s)
            reset_ok = (r1 == 0 and s1 == 1)
            hr, hs = read_stable(r), read_stable(s)      # must still hold
            hold_r = (hr == 0 and hs == 1)
            rs_pulse_low(s)                              # SET -> expect R=1 S=0
            r2, s2 = read_stable(r), read_stable(s)
            set_ok = (r2 == 1 and s2 == 0)
            hr2, hs2 = read_stable(r), read_stable(s)
            hold_s = (hr2 == 1 and hs2 == 0)
            cyc_ok = reset_ok and hold_r and set_ok and hold_s
            ok = ok and cyc_ok
            if (not cyc_ok) and fail_obs is None:
                fail_obs = (cyc, (r1, s1), (r2, s2))
        if fail_obs is None:
            fail_obs = (RS_CYCLES - 1, (r1, s1), (r2, s2))
        results.append((name, ok, fail_obs))
    return results


def rs_pages(results, all_ok):
    summary = ["2x RS FLIPFLOP"]
    for name, ok, _ in results:
        summary.append("%s %s" % (name, "PASS" if ok else "FAIL"))
    summary.append("")
    summary.append("ALL FF PASS" if all_ok else "** FAULT **")
    pages = [(summary, 0 if all_ok else 1, PAGE_MS)]
    for name, ok, fobs in results:
        if not ok:
            cyc, (r1, s1), (r2, s2) = fobs
            lines = ["%s FAIL" % name,
                     "RESET exp R0 S1",
                     " got R%d S%d %s" % (r1, s1, "ok" if (r1 == 0 and s1 == 1) else "BAD"),
                     "SET   exp R1 S0",
                     " got R%d S%d %s" % (r2, s2, "ok" if (r2 == 1 and s2 == 0) else "BAD"),
                     "(cycle %d)" % cyc]
            pages.append((lines, 0, DETAIL_MS))
    return pages


def print_rs(results, all_ok):
    print("Board: 2x RS flip-flop")
    for name, ok, fobs in results:
        cyc, (r1, s1), (r2, s2) = fobs
        print("  %-4s %s   (cycle %d)" % (name, "PASS" if ok else "FAIL", cyc))
        print("     RESET got R%d S%d (exp R0 S1)" % (r1, s1))
        print("     SET   got R%d S%d (exp R1 S0)" % (r2, s2))
    print("  RESULT:", "ALL FLIPFLOPS PASS" if all_ok else "FAULT DETECTED")


# ====== board 3: 2x XNOR ======
# header: 1:A 2:A~^B 3:B 4:NC 5:GND 6:VCC 7:NC 8:C 9:C~^D 10:D
# Output is XNOR = NOT(A XOR B) = 1 iff the two inputs are EQUAL. (If your gate
# is actually XOR, flip the `exp =` line below.) Output read with a pull-up,
# which is correct for a push-pull output and also covers an open-collector one.
XNOR_GATES = [("X1 ~(A^B)", 0, 2, 1),          # (name, inA_gp, inB_gp, out_gp)
              ("X2 ~(C^D)", 7, 9, 8)]
XNOR_INPUTS = [0, 2, 7, 9]
XNOR_VCC = 5             # pin 6
XNOR_GND = 4             # pin 5
XNOR_NC = [3, 6]


def xnor_test():
    drive(XNOR_VCC, 1)                          # VCC = logic high
    drive(XNOR_GND, 0)                          # GND = logic low
    for gp in XNOR_NC:
        release(gp)
    for _, _, _, y in XNOR_GATES:
        release(y, Pin.PULL_UP)
    for gp in XNOR_INPUTS:
        drive(gp, 0)
    time.sleep_ms(2)
    results = []
    for name, a_gp, b_gp, y_gp in XNOR_GATES:
        ok = True
        rows = []
        for a in (0, 1):
            for b in (0, 1):
                for gp in XNOR_INPUTS:
                    drive(gp, 0)
                drive(a_gp, a)
                drive(b_gp, b)
                time.sleep_us(SETTLE_US)
                got = read_stable(y_gp)
                exp = 1 if (a == b) else 0      # XNOR
                passed = (got == exp)
                ok = ok and passed
                rows.append((a, b, exp, got, passed))
        results.append((name, ok, rows))
    return results


def xnor_pages(results, all_ok):
    summary = ["2x XNOR TESTER"]
    for name, ok, _ in results:
        summary.append("%s %s" % (name, "PASS" if ok else "FAIL"))
    summary.append("")
    summary.append("ALL GATES PASS" if all_ok else "** FAULT **")
    pages = [(summary, 0 if all_ok else 1, PAGE_MS)]
    for name, ok, rows in results:
        if not ok:
            lines = ["%s FAIL" % name, "ab exp got"]
            for a, b, exp, got, p in rows:
                lines.append("%d%d  %d   %d  %s" % (a, b, exp, got, "ok" if p else "BAD"))
            pages.append((lines, 0, DETAIL_MS))
    return pages


def print_xnor(results, all_ok):
    print("Board: 2x XNOR")
    for name, ok, rows in results:
        print("  %-11s %s" % (name, "PASS" if ok else "FAIL"))
        for a, b, exp, got, p in rows:
            print("     a=%d b=%d exp=%d got=%d %s"
                  % (a, b, exp, got, "ok" if p else "<- MISMATCH"))
    print("  RESULT:", "ALL GATES PASS" if all_ok else "FAULT DETECTED")


# ====== orchestration ======
RECHECK_TICKS = 6        # while a page shows, re-test every RECHECK_TICKS*100 ms


def run_once(verbose=True):
    if verbose:
        print("\n=== PCB tester ===")
    if BOARD == "nand":
        kind, results = "nand", nand_test()
    elif BOARD == "rs":
        kind, results = "rs", rs_test()
    elif BOARD == "xnor":
        kind, results = "xnor", xnor_test()
    else:
        # auto: NAND, then RS, then fall back to XNOR (shown regardless).
        nres = nand_test()
        if any(ok for _, ok, _ in nres):
            kind, results = "nand", nres
        else:
            if verbose:
                print("No NAND gate behaved correctly -> trying RS flip-flop")
            rres = rs_test()
            if any(ok for _, ok, _ in rres):
                kind, results = "rs", rres
            else:
                if verbose:
                    print("No RS flip-flop worked either -> testing as XNOR")
                kind, results = "xnor", xnor_test()

    all_ok = all(ok for _, ok, _ in results)
    overall_ok = all_ok
    orient_fwd = None                             # part of the change signature

    if kind == "nand":
        vol_info = None
        if ORIENT_CHECK:                          # measure V_OL of the wired gate
            try:
                oname, vol, fwd = orient_test()
                vol_info = (oname, vol, fwd)
                orient_fwd = fwd
                if verbose:
                    print("  ORIENT %s: V_OL = %.3f V under ~1k load -> %s"
                          % (oname, vol, "forward (ok)" if fwd else "REVERSED?"))
                overall_ok = overall_ok and fwd   # blink the LED if it looks reversed
            except Exception as exc:              # never let the check freeze the rig
                if verbose:
                    print("  ORIENT check skipped (%s)" % exc)
        if verbose:
            print_nand(results, all_ok)
        pages = nand_pages(results, all_ok, vol_info)
        if vol_info:
            pages.append(orient_page(*vol_info))  # plus the verdict page
    elif kind == "rs":
        if verbose:
            print_rs(results, all_ok)
        pages = rs_pages(results, all_ok)
    else:
        if verbose:
            print_xnor(results, all_ok)
        pages = xnor_pages(results, all_ok)

    # stable identity of the result: board kind, pass/fail per unit, and the
    # forward/reversed verdict (so swapping a good <-> reversed NAND counts as a
    # change even though both pass). Excludes the noisy raw V_OL on purpose.
    sig = (kind, tuple((name, ok) for name, ok, _ in results), orient_fwd)
    return pages, overall_ok, sig


def show_cycle(pages, all_ok, sig):
    """Show each page for its dwell; meanwhile re-test periodically. Return True
    as soon as the result changes (caller restarts the cycle), else False."""
    for lines, inv, ms in pages:
        render_lines(lines, inv)
        waited = 0
        ticks = 0
        while waited < ms:
            if all_ok:
                led.on()
            else:
                led.toggle()                      # fast blink on any fault
            time.sleep_ms(100)
            waited += 100
            ticks += 1
            if ticks >= RECHECK_TICKS:
                ticks = 0
                if run_once(verbose=False)[2] != sig:
                    return True                   # board / result changed
    return False


def main():
    render_lines(["PCB TESTER", "", "auto-detecting", "board ..."])
    pages, all_ok, sig = run_once()
    while True:
        if show_cycle(pages, all_ok, sig):
            print("** change detected -> restarting display **")
        pages, all_ok, sig = run_once()           # fresh result; restart from page 1


if __name__ == "__main__":
    main()
