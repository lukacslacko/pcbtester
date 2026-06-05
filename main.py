# main.py
# ---------------------------------------------------------------------------
# Breadboard PCB tester for a 3x open-collector NAND board.
#
# DUT (device under test) 10-pin header, in header order:
#   1:A  2:B  3:~(A&B)  4:C  5:D  6:~(C&D)  7:E  8:F  9:~(E&F)  10:GND
#
# The board has no VCC pin: each gate is an open-collector NAND, so its
# output only pulls LOW (to GND) and otherwise floats. We enable the Pico's
# internal pull-ups on the three read pins to provide the required pull-up,
# drive the six inputs at 3.3 V, and check each gate's truth table.
#
# Runs on MicroPython. Copy to the Pico as main.py (plus ssd1306.py for the
# display) and it runs at power-up. Results are shown three ways:
#   - SBC-OLED01 (SSD1306 128x64 I2C): per-gate status + overall verdict
#   - onboard LED: steady = all gates pass, fast blink = at least one fault
#   - USB serial REPL: full per-input-combination log
# The OLED is optional at runtime: if ssd1306.py or the panel is missing, the
# tester keeps working via serial + LED.
# ---------------------------------------------------------------------------

from machine import Pin, I2C
import time

# ---- Pin assignment (Pico GPIO numbers; see README wiring table) ----
# GPIOs are laid out in DUT-header order so the jumpers run straight down the
# Pico's left edge without crossing. Each consecutive triple is one gate:
#   GP0,GP1 -> GP2   |   GP3,GP4 -> GP5   |   GP6,GP7 -> GP8
#
# Inputs we DRIVE into the DUT:
A = Pin(0, Pin.OUT)
B = Pin(1, Pin.OUT)
C = Pin(3, Pin.OUT)
D = Pin(4, Pin.OUT)
E = Pin(6, Pin.OUT)
F = Pin(7, Pin.OUT)

# Outputs we READ from the DUT. Open-collector -> enable internal pull-ups:
Y1 = Pin(2, Pin.IN, Pin.PULL_UP)   # ~(A & B)
Y2 = Pin(5, Pin.IN, Pin.PULL_UP)   # ~(C & D)
Y3 = Pin(8, Pin.IN, Pin.PULL_UP)   # ~(E & F)

led = Pin("LED", Pin.OUT)

# ---- SBC-OLED01 status display (SSD1306, 128x64, I2C) ----
# On I2C1: SDA=GP26 (phys 31), SCL=GP27 (phys 32). Powered from 3V3 + GND.
# Kept on the Pico's right edge, away from the DUT jumpers on the left.
# If the display is absent or miswired we fall back to serial + LED.
OLED_W, OLED_H = 128, 64
oled = None
try:
    from ssd1306 import SSD1306_I2C
    _i2c = I2C(1, sda=Pin(26), scl=Pin(27), freq=400_000)
    oled = SSD1306_I2C(OLED_W, OLED_H, _i2c, addr=0x3C)
    oled.fill(0)
    oled.text("3x NAND TESTER", 0, 0)
    oled.text("starting...", 0, 16)
    oled.show()
except Exception as exc:                       # noqa: BLE001 - any I2C/import error
    print("OLED unavailable (%s); serial + LED only" % exc)


PAGE_MS = 1500           # how long each OLED page is shown before rotating


def render_summary(gate_results, all_ok):
    """Page 0: one line per gate (PASS/FAIL) plus the overall verdict."""
    oled.invert(0 if all_ok else 1)             # flash inverse on failure
    oled.fill(0)
    oled.text("3x NAND TESTER", 0, 0)
    y = 16
    for name, ok, _rows in gate_results:        # e.g. "G1 ~(A&B) PASS"
        oled.text("%s %s" % (name, "PASS" if ok else "FAIL"), 0, y)
        y += 11
    oled.hline(0, 50, OLED_W, 1)
    oled.text("ALL GATES PASS" if all_ok else "** FAULT **", 0, 54)
    oled.show()


def render_detail(name, rows):
    """Detail page for a failing gate: its full truth table, bad rows flagged."""
    oled.invert(0)                              # keep detail readable
    oled.fill(0)
    oled.text("%s FAIL" % name, 0, 0)
    oled.text("ab exp got", 0, 13)
    y = 25
    for a, b, exp, got, passed in rows:
        oled.text("%d%d  %d   %d  %s" % (a, b, exp, got, "ok" if passed else "BAD"),
                  0, y)
        y += 10
    oled.show()


def build_pages(gate_results, all_ok):
    """Summary first, then one detail page per failing gate."""
    pages = [("summary", gate_results, all_ok)]
    for name, ok, rows in gate_results:
        if not ok:
            pages.append(("detail", name, rows))
    return pages


def show_page(page):
    if oled is None:
        return
    if page[0] == "summary":
        render_summary(page[1], page[2])
    else:
        render_detail(page[1], page[2])


# (name, input_a, input_b, output)
GATES = [
    ("G1 ~(A&B)", A, B, Y1),
    ("G2 ~(C&D)", C, D, Y2),
    ("G3 ~(E&F)", E, F, Y3),
]

ALL_INPUTS = [A, B, C, D, E, F]
SETTLE_US = 300          # let the open-collector node settle through the pull-up


def read_stable(pin, samples=5):
    """Majority-vote a few samples to reject the occasional glitch."""
    s = 0
    for _ in range(samples):
        s += pin.value()
        time.sleep_us(50)
    return 1 if s * 2 > samples else 0


def test_gate(name, in_a, in_b, out):
    ok = True
    rows = []
    for a in (0, 1):
        for b in (0, 1):
            # Park every input LOW, then set just this gate's two inputs.
            for p in ALL_INPUTS:
                p.value(0)
            in_a.value(a)
            in_b.value(b)
            time.sleep_us(SETTLE_US)
            got = read_stable(out)
            expected = 0 if (a and b) else 1        # NAND truth table
            passed = (got == expected)
            ok = ok and passed
            rows.append((a, b, expected, got, passed))
    return ok, rows


def run_once():
    print("\n=== 3x open-collector NAND test ===")
    gate_results = []                            # list of (name, ok, rows)
    all_ok = True
    for name, in_a, in_b, out in GATES:
        ok, rows = test_gate(name, in_a, in_b, out)
        all_ok = all_ok and ok
        gate_results.append((name, ok, rows))
        print("%-11s %s" % (name, "PASS" if ok else "FAIL"))
        for a, b, exp, got, p in rows:
            print("   a=%d b=%d  expect=%d  read=%d  %s"
                  % (a, b, exp, got, "ok" if p else "<-- MISMATCH"))
    print("RESULT:", "ALL GATES PASS" if all_ok else "FAULT DETECTED")
    return gate_results, all_ok


def dwell(ms, all_ok):
    """Wait `ms` while keeping the LED indicator alive (steady=pass, blink=fail)."""
    waited = 0
    while waited < ms:
        if all_ok:
            led.on()
        else:
            led.toggle()           # fast blink on failure
        time.sleep_ms(100)
        waited += 100


def main():
    while True:
        gate_results, all_ok = run_once()
        # Rotate: summary page, then a detail page per failing gate. After one
        # full cycle we re-test (so swapping in a new DUT refreshes the screen).
        pages = build_pages(gate_results, all_ok)
        for page in pages:
            show_page(page)
            dwell(PAGE_MS, all_ok)


if __name__ == "__main__":
    main()
