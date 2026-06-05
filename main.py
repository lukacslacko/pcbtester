# main.py
# ---------------------------------------------------------------------------
# Breadboard PCB tester (Raspberry Pi Pico, MicroPython) for two boards that
# share the same 10-pin header. All ten header pins are wired to GP0..GP9
# (DUT pin i -> GP(i-1)); NO hard ground is used, so VCC/GND for each board
# are synthesised by driving the matching GPIO high/low. One wiring, two boards.
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
# Auto-detection: run the NAND test first; if not a single gate behaves like a
# NAND, assume the RS board and test that instead. Set BOARD below to force one.
#
# Output: SBC-OLED01 (SSD1306) with page rotation, onboard LED, USB serial.
# Needs ssd1306.py on the Pico too (optional; falls back to serial + LED).
# ---------------------------------------------------------------------------

from machine import Pin, I2C
import time

# ====== board selection ======
BOARD = "auto"           # "auto" (NAND-probe, then RS), "nand", or "rs"

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
PAGE_MS = 1500           # ms each OLED page is shown before rotating
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


def show_page(page):
    lines, inv = page
    render_lines(lines, inv)


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


def nand_pages(results, all_ok):
    summary = ["3x NAND TESTER"]
    for name, ok, _ in results:
        summary.append("%s %s" % (name, "PASS" if ok else "FAIL"))
    summary.append("")
    summary.append("ALL GATES PASS" if all_ok else "** FAULT **")
    pages = [(summary, 0 if all_ok else 1)]
    for name, ok, rows in results:
        if not ok:
            lines = ["%s FAIL" % name, "ab exp got"]
            for a, b, exp, got, p in rows:
                lines.append("%d%d  %d   %d  %s" % (a, b, exp, got, "ok" if p else "BAD"))
            pages.append((lines, 0))
    return pages


def print_nand(results, all_ok):
    print("Board: 3x open-collector NAND")
    for name, ok, rows in results:
        print("  %-11s %s" % (name, "PASS" if ok else "FAIL"))
        for a, b, exp, got, p in rows:
            print("     a=%d b=%d exp=%d got=%d %s"
                  % (a, b, exp, got, "ok" if p else "<- MISMATCH"))
    print("  RESULT:", "ALL GATES PASS" if all_ok else "FAULT DETECTED")


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
    pages = [(summary, 0 if all_ok else 1)]
    for name, ok, fobs in results:
        if not ok:
            cyc, (r1, s1), (r2, s2) = fobs
            lines = ["%s FAIL" % name,
                     "RESET exp R0 S1",
                     " got R%d S%d %s" % (r1, s1, "ok" if (r1 == 0 and s1 == 1) else "BAD"),
                     "SET   exp R1 S0",
                     " got R%d S%d %s" % (r2, s2, "ok" if (r2 == 1 and s2 == 0) else "BAD"),
                     "(cycle %d)" % cyc]
            pages.append((lines, 0))
    return pages


def print_rs(results, all_ok):
    print("Board: 2x RS flip-flop")
    for name, ok, fobs in results:
        cyc, (r1, s1), (r2, s2) = fobs
        print("  %-4s %s   (cycle %d)" % (name, "PASS" if ok else "FAIL", cyc))
        print("     RESET got R%d S%d (exp R0 S1)" % (r1, s1))
        print("     SET   got R%d S%d (exp R1 S0)" % (r2, s2))
    print("  RESULT:", "ALL FLIPFLOPS PASS" if all_ok else "FAULT DETECTED")


# ====== orchestration ======
def run_once():
    print("\n=== PCB tester ===")
    if BOARD == "nand":
        kind, results = "nand", nand_test()
    elif BOARD == "rs":
        kind, results = "rs", rs_test()
    else:
        nres = nand_test()
        if any(ok for _, ok, _ in nres):
            kind, results = "nand", nres
        else:
            print("No NAND gate behaved correctly -> testing as RS flip-flop")
            kind, results = "rs", rs_test()

    all_ok = all(ok for _, ok, _ in results)
    if kind == "nand":
        print_nand(results, all_ok)
        pages = nand_pages(results, all_ok)
    else:
        print_rs(results, all_ok)
        pages = rs_pages(results, all_ok)
    return pages, all_ok


def dwell(ms, all_ok):
    """Wait `ms` while keeping the LED alive (steady=pass, blink=fail)."""
    waited = 0
    while waited < ms:
        if all_ok:
            led.on()
        else:
            led.toggle()
        time.sleep_ms(100)
        waited += 100


def main():
    render_lines(["PCB TESTER", "", "auto-detecting", "board ..."])
    while True:
        pages, all_ok = run_once()
        for page in pages:
            show_page(page)
            dwell(PAGE_MS, all_ok)


if __name__ == "__main__":
    main()
