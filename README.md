# Breadboard PCB Tester — 3× Open-Collector NAND

A Raspberry Pi Pico–based functional tester for a small PCB that contains three
2-input **open-collector NAND** gates. You plug the board's 10-pin header into a
breadboard next to the Pico, jumper it to the GPIOs per the table below, and the
Pico exercises every gate's full truth table and reports PASS/FAIL — on an
**SBC-OLED01 display** (and the onboard LED) for at-a-glance results, plus the USB
serial console for the full per-combination log.

---

## 1. The board under test (DUT)

10-pin header, in order:

| Pin | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|-----|---|---|---|---|---|---|---|---|---|----|
| Net | A | B | ~(A&B) | C | D | ~(C&D) | E | F | ~(E&F) | GND |

Three independent gates: **G1 = ~(A&B)**, **G2 = ~(C&D)**, **G3 = ~(E&F)**.

NAND truth table (what each output should do):

| in_a | in_b | output |
|------|------|--------|
| 0 | 0 | 1 |
| 0 | 1 | 1 |
| 1 | 0 | 1 |
| 1 | 1 | 0 |

### Why there is no VCC pin
The outputs are **open-collector**: the output only ever pulls *down* to GND (when
both inputs are high). For any other input combination the output transistor is
off and the pin **floats** — it has no way to drive itself high. It needs an
external **pull-up resistor** to be read as a logic "1". The whole board therefore
needs only GND plus the logic levels you apply — no separate supply rail.

**Key trick:** the Pico has built-in ~50–80 kΩ pull-ups you can switch on in
software. We enable them on the three output pins, so **no external resistors are
required** for a basic test.

---

## 2. Bill of materials

- 1× Raspberry Pi Pico (or Pico W / Pico 2) with male headers soldered
- 1× solderless breadboard (full size, with a center channel)
- 1× **SBC-OLED01** status display (Joy-IT 0.96″ SSD1306, 128×64, I²C)
- 14× male–male jumper wires (10 for the DUT + 4 for the OLED)
- USB cable (micro-USB / USB-C to match your Pico) for power + serial
- *(optional, for robustness)* 6× 1 kΩ resistors — series protection on the drive lines
- *(optional)* 3× 4.7 kΩ–10 kΩ resistors — stronger external pull-ups on the outputs

You do **not** need an external power supply; the Pico is powered over USB, and
both the DUT and the OLED (~15 mA) run off the Pico's own 3V3 rail, well within
its ~300 mA budget.

---

## 3. Pin mapping (the source of truth)

GPIOs are assigned **in DUT-header order** so the ten jumpers run monotonically
down the Pico's left edge and never cross each other. The Pico's GND pins fall at
physical pins 3, 8, 13, 18; we route the DUT's GND (its last pin) to the one at
**physical pin 13**, which sits *after* all nine signal GPIOs, keeping the whole
sequence in order. Bonus: each consecutive GPIO triple is exactly one gate
(GP0,GP1→GP2 · GP3,GP4→GP5 · GP6,GP7→GP8), matching the header's A,B,Y grouping.

| DUT pin | Net | Direction | Pico GPIO | Pico physical pin |
|:------:|:------:|:---------:|:---------:|:-----------------:|
| 1 | A        | Pico → DUT (drive) | GP0 | 1 |
| 2 | B        | Pico → DUT (drive) | GP1 | 2 |
| 3 | ~(A&B) Y1| DUT → Pico (read)  | GP2 | 4 |
| 4 | C        | Pico → DUT (drive) | GP3 | 5 |
| 5 | D        | Pico → DUT (drive) | GP4 | 6 |
| 6 | ~(C&D) Y2| DUT → Pico (read)  | GP5 | 7 |
| 7 | E        | Pico → DUT (drive) | GP6 | 9 |
| 8 | F        | Pico → DUT (drive) | GP7 | 10 |
| 9 | ~(E&F) Y3| DUT → Pico (read)  | GP8 | 11 |
| 10| GND      | common ground      | GND | 13 |

> Going down the header, every wire lands on a strictly-lower Pico pin, so the
> jumpers fan gently downward and never tangle. A perfectly horizontal 1:1
> mapping is impossible (the header is a solid 10-pin strip but the Pico's edge
> has GND gaps), but monotonic-and-non-crossing is the next best thing.

### OLED status display (SBC-OLED01)

The SBC-OLED01 is an SSD1306 128×64 I²C module with a 4-pin header. It lives on
the Pico's **right edge**, where pins 31–36 form a tidy power-and-I²C cluster, so
it never competes with the DUT jumpers on the left. We use **I²C1 on GP26/GP27**.

| OLED pin | Net | Pico pin | Pico physical pin |
|:--------:|:---:|:--------:|:-----------------:|
| VCC / VDD | 3.3 V | 3V3      | 36 |
| GND       | gnd   | GND      | 33 |
| SCL / SCK | clock | GP27 (I²C1 SCL) | 32 |
| SDA       | data  | GP26 (I²C1 SDA) | 31 |

> **Check the silkscreen.** SSD1306 breakouts vary in pin order (some are
> `GND VCC SCL SDA`, others `VCC GND ...`). Match the *labels* on your module, not
> the physical position. The module is 3.3 V/5 V tolerant; powering from the
> Pico's 3V3 keeps the I²C levels clean. Default I²C address is `0x3C`.

---

## 4. Breadboard layout

Place the Pico straddling the center channel near one end. Put the DUT 10-pin
header **parallel to the Pico's left edge** and the OLED off the **right edge**.
Then run the 10 DUT jumpers (left) and 4 OLED jumpers (right).

```
       DUT header (parallel)         left edge / right edge of Pico
                                          (USB facing up/away)
  ┌────────┐                        ┌───────────────────┐
  │ 1  A   │──► GP0   (phys 1)  GP0 │ 1               40│ VBUS
  │ 2  B   │──► GP1   (phys 2)  GP1 │ 2               39│ VSYS
  │ 3  Y1  │──► GP2   (phys 4)  GND │ 3               38│ GND
  │ 4  C   │──► GP3   (phys 5)  GP2 │ 4               37│ 3V3_EN
  │ 5  D   │──► GP4   (phys 6)  GP3 │ 5               36│ 3V3 ──► OLED VCC
  │ 6  Y2  │──► GP5   (phys 7)  GP4 │ 6               35│ ADC_VREF
  │ 7  E   │──► GP6   (phys 9)  GP5 │ 7               34│ GP28
  │ 8  F   │──► GP7   (phys10)  GND │ 8               33│ GND ──► OLED GND
  │ 9  Y3  │──► GP8   (phys11)  GP6 │ 9               32│ GP27 ─► OLED SCL
  │ 10 GND │──► GND   (phys13)  GP7 │ 10              31│ GP26 ─► OLED SDA
  └────────┘                    GP8 │ 11              30│ RUN
                                GP9 │ 12              29│ GP22       ┌──────────┐
   DUT GND lands on phys 13 ──► GND │ 13                │            │ SBC-OLED01│
   (after all the GPIOs)            │ ...               │            │  128x64   │
                                    └───────────────────┘            └──────────┘
```

On the **left**, reading top to bottom, both the DUT and the Pico columns only
ever move *downward* — that's what keeps the DUT jumpers from crossing. On the
**right**, the four OLED wires all land in the pin 31–36 cluster.

Each breadboard row (the 5 holes a–e on one side of the channel) is one electrical
node, so "plug DUT pin into a hole in the same row as the jumper's other end."

---

## 5. Step-by-step wiring

1. **Power off** — leave the Pico unplugged from USB while you wire.
2. Seat the Pico across the center channel so its left-edge pins are accessible.
3. Insert the DUT 10-pin header into the breadboard, parallel to the Pico.
4. Connect **GND first**: DUT pin 10 → Pico GND at physical pin 13.
5. Now just work straight down the header — each wire goes one or two rows lower
   on the Pico than the previous: A→GP0, B→GP1, Y1→GP2, C→GP3, D→GP4, Y2→GP5,
   E→GP6, F→GP7, Y3→GP8.
6. Wire the **OLED** on the right edge (match its silkscreen labels):
   VCC→3V3 (pin 36), GND→GND (pin 33), SCL→GP27 (pin 32), SDA→GP26 (pin 31).
7. Double-check against the tables — a swapped input/output line, or swapped
   SDA/SCL, is the #1 mistake.
8. *(Optional protection — recommended if you don't know the DUT's internals:)*
   put a **1 kΩ resistor in series** on each of the six drive lines. This caps the
   current if an input is internally tied low/shorted, protecting both boards. It
   does not affect the logic.
9. *(Optional:)* add **4.7 kΩ–10 kΩ** from each output (Y1/Y2/Y3) to the Pico's
   **3V3** pin (physical pin 36) for snappier highs under heavier load. The
   internal pull-ups already cover a basic static test, so this is just insurance.

---

## 6. Load the firmware

The tester runs in **MicroPython**.

1. **Install MicroPython** (one time): hold the Pico's **BOOTSEL** button while
   plugging in USB. It mounts as a USB drive (`RPI-RP2`). Drag the MicroPython
   `.uf2` onto it (download from raspberrypi.com or via Thonny's installer). The
   Pico reboots running MicroPython.
2. **Install Thonny** (https://thonny.org), set the interpreter to
   *MicroPython (Raspberry Pi Pico)* via the bottom-right corner.
3. Copy the **OLED driver** to the Pico: open `ssd1306.py` from this folder and
   **File → Save as… → Raspberry Pi Pico**, keeping the name `ssd1306.py`.
   (Alternatively, Thonny → *Tools → Manage packages* → install `micropython-ssd1306`.)
4. Open `main.py` from this folder, then **File → Save as… → Raspberry Pi Pico**,
   and save it there **as `main.py`**. Saving as `main.py` makes it auto-run on
   every power-up, so the rig works standalone afterward.

> The Pico must end up with **two** files: `main.py` and `ssd1306.py`. If the
> driver is missing, `main.py` still runs — it just prints "OLED unavailable" and
> falls back to serial + the onboard LED.

> Prefer C/C++ SDK or rshell/ampy? Same pin map applies — just port `main.py`.
> The logic is: drive GP0,GP1,GP3,GP4,GP6,GP7; read GP2,GP5,GP8 with pull-ups on;
> OLED on I²C1 (GP26 SDA, GP27 SCL) at address 0x3C.

---

## 7. Run and read the result

- With `main.py` on the Pico, it runs automatically at power-up and **repeats the
  test about every 2 seconds**.
- Open the serial console (Thonny REPL, or `screen`/`minicom`/PuTTY at the Pico's
  USB serial port) to see the full report:

```
=== 3x open-collector NAND test ===
G1 ~(A&B)   PASS
   a=0 b=0  expect=1  read=1  ok
   a=0 b=1  expect=1  read=1  ok
   a=1 b=0  expect=1  read=1  ok
   a=1 b=1  expect=0  read=0  ok
G2 ~(C&D)   PASS
   ...
G3 ~(E&F)   PASS
   ...
RESULT: ALL GATES PASS
```

- **OLED display**: shows the live verdict at a glance — no laptop needed. It
  **rotates through pages every ~1.5 s**: first a summary, then one detail page for
  *each* failing gate, then back to the summary.

  ```
  PAGE 1 — summary        PAGE 1 — summary        PAGE 2 — detail (per fault)
  (all good)              (a fault)               G2 ~(C&D) FAIL
  3x NAND TESTER          3x NAND TESTER          ab exp got
  G1 ~(A&B) PASS          G1 ~(A&B) PASS          00  1   1  ok
  G2 ~(C&D) PASS          G2 ~(C&D) FAIL          01  1   1  ok
  G3 ~(E&F) PASS          G3 ~(E&F) PASS          10  1   1  ok
  ----------------        ----------------        11  0   1  BAD
  ALL GATES PASS          ** FAULT **
                          (screen inverts)
  ```

  The summary inverts (white background) on any failure so a bad board is obvious
  across the bench. Each detail page then names the failing gate and shows its full
  4-row truth table, flagging the exact input combination(s) that misbehaved
  (`BAD`) — in the example above, gate 2 never pulls its output low: at C=1, D=1 it
  reads high (1) when it should be low (0), the signature of an open output
  transistor or a cold solder joint. With all gates passing there's only the one
  summary page, so the screen sits still.
- **Onboard LED**: steady ON = all three gates pass; fast blink = at least one
  mismatch. A redundant at-a-glance indicator that works even if the OLED is
  unplugged.
- The **serial console** still prints every gate's full truth table each run; the
  OLED detail pages mirror that for the failing gates without needing a laptop.

> Tune the rotation speed with `PAGE_MS` near the top of `main.py` (milliseconds
> per page; default 1500).

---

## 8. Interpreting failures

| Symptom | Likely cause |
|---|---|
| One gate's `a=1 b=1` row reads **1** instead of 0 | Output stuck high — open output transistor, broken solder joint on that output, or that gate's two inputs not reaching the transistor bases |
| A gate's output reads **0** for every combination | Output shorted to GND, or that gate permanently conducting (shorted transistor) |
| **All** outputs stuck high | GND not connected, or you forgot the pull-ups (in this firmware they're enabled — check GND first) |
| **All** outputs stuck low | A drive line shorted to an output, or 3V3/GND swapped |
| One gate wrong but its neighbor's inputs change it | Cross-coupling / solder bridge between adjacent nets |
| Results flicker between PASS/FAIL | Loose jumper or DUT not fully seated; raise `SETTLE_US`, add the external pull-ups |
| OLED blank, serial prints "OLED unavailable" | `ssd1306.py` not copied, SDA/SCL swapped, no power (VCC/GND), or wrong address — try `0x3D` in `main.py` |
| OLED text garbled or partly drawn | Loose I²C wire or too-long jumpers; lower I²C `freq` to `100_000` in `main.py` |

Because the firmware drives only one gate's inputs at a time (others parked LOW),
a fault is isolated to a specific gate and a specific input combination, which
points you straight at the offending net or component.

---

## 9. How the test works (theory)

For each gate, for each of the four input combinations:
1. Park all six inputs LOW.
2. Drive that gate's two inputs to the test combination at 3.3 V.
3. Wait ~300 µs for the open-collector node to settle through the pull-up.
4. Sample the output 5× and majority-vote.
5. Compare against `expected = NOT(a AND b)`.

A logic "1" read means the output transistor is **off** and the pull-up won the
node; a "0" means the output is actively pulling to GND. That's exactly the
open-collector NAND behaviour, so a correct board passes all 12 checks
(3 gates × 4 rows).

---

## 10. Adapting to other boards

This rig is a general pattern. For a different DUT:
- Update the **pin mapping table** and the `Pin(...)` assignments at the top of
  `main.py`.
- For push-pull (totem-pole) outputs, read with `Pin.IN` (no pull-up) instead of
  `Pin.PULL_UP`.
- For boards that need VCC, feed it from the Pico's **3V3** pin (pin 36, ~300 mA
  budget) or a bench supply sharing GND with the Pico.
- Replace `test_gate` / `GATES` with the truth table or expected I/O of the new
  device.

---

## 11. License

This project is released under the [MIT License](LICENSE).

`ssd1306.py` is the canonical OLED driver from the
[MicroPython project](https://github.com/micropython/micropython-lib), also under
the MIT License. It is bundled here for convenience so the Pico ends up with both
required files; all credit for it goes to the MicroPython authors.
