# Breadboard PCB Tester — Raspberry Pi Pico

A Raspberry Pi Pico–based functional tester for small PCBs on a shared **10-pin
header**. It currently knows three boards and **auto-detects** which one is
plugged in, exercising it and reporting PASS/FAIL on an **SBC-OLED01 display**
(with page rotation), the onboard LED, and the USB serial console:

1. **3× open-collector NAND** — three 2-input NAND gates.
2. **2× RS flip-flop** — two cross-coupled set/reset latches.
3. **2× XNOR** — two 2-input XNOR gates.

Detection order: NAND, then RS, then **XNOR as the fallback** (if no NAND gate and
no RS latch behaves, it's tested and reported as XNOR).

All ten header pins go to GPIOs **GP0–GP9** (no hard ground), so the supply pins
of each board are synthesised in firmware. One wiring tests all three boards; you
swap boards without rewiring.

---

## 1. The boards under test (DUTs)

### Board 1 — 3× open-collector NAND

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

**Why there is no VCC pin.** The outputs are **open-collector**: an output only
ever pulls *down* to GND (when both inputs are high). Otherwise the output
transistor is off and the pin **floats** — it needs a **pull-up** to read as "1".
So the board needs only GND plus the logic levels you apply. The Pico's built-in
~50–80 kΩ pull-ups, switched on in software on the three output pins, supply that
— **no external resistors required**.

### Board 2 — 2× RS flip-flop

Same 10-pin header, different pinout:

| Pin | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|-----|---|---|---|---|---|---|---|---|---|----|
| Net | VCC | R1 | NC | S1 | NC | GND | NC | R2 | NC | S2 |

Two independent cross-coupled latches: **FF1** = (R1, S1) and **FF2** = (R2, S2).
Each of R/S is an **open node pulled up to VCC on the board**, and is *both* an
input and an output: you flip the latch by **sinking a node low** (the lines
tolerate being shorted to ground), and you read the state back off the same two
nodes. Pulling **R low** latches **R=0, S=1**; pulling **S low** latches
**R=1, S=0**; the state **holds** after you release the node.

The board draws so little current that a logic-high GPIO is enough for VCC and a
logic-low GPIO is enough for GND — which is exactly how the tester powers it.

### Board 3 — 2× XNOR

Same 10-pin header, a third pinout:

| Pin | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|-----|---|---|---|---|---|---|---|---|---|----|
| Net | A | A~^B | B | NC | GND | VCC | NC | C | C~^D | D |

Two independent gates: **X1 = ~(A^B)** on pins 1/2/3 and **X2 = ~(C^D)** on pins
8/9/10. The output is **XNOR** — `1` exactly when the two inputs are **equal**:

| in_a | in_b | output |
|------|------|--------|
| 0 | 0 | 1 |
| 0 | 1 | 0 |
| 1 | 0 | 0 |
| 1 | 1 | 1 |

Again, VCC is a driven logic-high GPIO and GND a driven logic-low one. The output
is read with the Pico's pull-up enabled, which is correct for a push-pull output
and also covers an open-collector one.

> The output pins are written `A~^B` / `C~^D` to mean *XNOR* (the board's name),
> not bitwise XOR. If your gate is actually **XOR**, change one line in `main.py`
> — `exp = 1 if (a == b) else 0` → `exp = 1 if (a != b) else 0`.

---

## 2. Bill of materials

- 1× Raspberry Pi Pico (or Pico W / Pico 2) with male headers soldered
- 1× solderless breadboard (full size, with a center channel)
- 1× **SBC-OLED01** status display (Joy-IT 0.96″ SSD1306, 128×64, I²C)
- 14× male–male jumper wires (10 for the DUT + 4 for the OLED)
- USB cable (micro-USB / USB-C to match your Pico) for power + serial
- Any of the DUT boards (3× NAND, 2× RS flip-flop, 2× XNOR)

No extra resistors are needed: the NAND/XNOR outputs use the Pico's internal
pull-ups and the RS nodes use the board's own pull-ups. (Skip the series resistors
the NAND-only build mentioned — see §5; they would stop the RS latches flipping.)

You do **not** need an external power supply; the Pico is powered over USB, the
OLED (~15 mA) and both DUTs run off the Pico's 3V3 rail / GPIOs, well within
budget.

---

## 3. Pin mapping (the source of truth)

**Every header pin goes to a GPIO.** DUT pin *i* → **GP(i−1)**, i.e. GP0…GP9, all
on the Pico's left edge at physical pins 1, 2, 4, 5, 6, 7, 9, 10, 11, **12**.
No header pin connects to the Pico's hard ground — instead the firmware *drives*
whichever pin is GND low and whichever is VCC high. That is the whole reason one
wiring can test all three boards, whose supply pins sit in different places.

| DUT pin | Pico GPIO | Pico physical pin |
|:------:|:---------:|:-----------------:|
| 1 | GP0 | 1 |
| 2 | GP1 | 2 |
| 3 | GP2 | 4 |
| 4 | GP3 | 5 |
| 5 | GP4 | 6 |
| 6 | GP5 | 7 |
| 7 | GP6 | 9 |
| 8 | GP7 | 10 |
| 9 | GP8 | 11 |
| 10| GP9 | 12 |

The wires still run monotonically down the left edge (GP0…GP9, skipping the GND
pins at physical 3 and 8), so they never cross.

> ### ⚠ If you built the NAND-only version: move ONE jumper
> The earlier single-board wiring sent DUT pin 10 to the Pico's hard **GND
> (physical 13)**. The RS board has a live signal (**S2**) on pin 10 and its
> ground on pin 6, so a hard ground there would short S2 out. **Move the pin-10
> jumper one pin up, from GND (phys 13) to GP9 (phys 12).** The NAND board still
> works (the firmware now drives GP9 low as its ground); the RS board now works
> too. This is the only change, and after it you never rewire again.

How each GPIO is used depends on the detected board:

| GP | phys | NAND board (pin) | RS board (pin) | XNOR board (pin) |
|:--:|:----:|:-----------------|:---------------|:-----------------|
| GP0 | 1  | A — drive            | **VCC — drive HIGH** | A — drive |
| GP1 | 2  | B — drive            | R1 — pulse low / read | ~(A^B) — read (pull-up) |
| GP2 | 4  | ~(A&B) — read (pull-up) | NC | B — drive |
| GP3 | 5  | C — drive            | S1 — pulse low / read | NC |
| GP4 | 6  | D — drive            | NC | **GND — drive LOW** |
| GP5 | 7  | ~(C&D) — read (pull-up) | **GND — drive LOW** | **VCC — drive HIGH** |
| GP6 | 9  | E — drive            | NC | NC |
| GP7 | 10 | F — drive            | R2 — pulse low / read | C — drive |
| GP8 | 11 | ~(E&F) — read (pull-up) | NC | ~(C^D) — read (pull-up) |
| GP9 | 12 | **GND — drive LOW**  | S2 — pulse low / read | D — drive |

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
    DUT header (parallel)            left edge / right edge of Pico
   (nets shown for NAND/RS)               (USB facing up/away)
  ┌────────────┐                      ┌───────────────────┐
  │ 1  A /VCC  │─► GP0  (phys 1)  GP0 │ 1               40│ VBUS
  │ 2  B /R1   │─► GP1  (phys 2)  GP1 │ 2               39│ VSYS
  │ 3  Y1/NC   │─► GP2  (phys 4)  GND │ 3               38│ GND
  │ 4  C /S1   │─► GP3  (phys 5)  GP2 │ 4               37│ 3V3_EN
  │ 5  D /NC   │─► GP4  (phys 6)  GP3 │ 5               36│ 3V3 ──► OLED VCC
  │ 6  Y2/GND  │─► GP5  (phys 7)  GP4 │ 6               35│ ADC_VREF
  │ 7  E /NC   │─► GP6  (phys 9)  GP5 │ 7               34│ GP28
  │ 8  F /R2   │─► GP7  (phys10)  GND │ 8               33│ GND ──► OLED GND
  │ 9  Y3/NC   │─► GP8  (phys11)  GP6 │ 9               32│ GP27 ─► OLED SCL
  │ 10 GND/S2  │─► GP9  (phys12)  GP7 │ 10              31│ GP26 ─► OLED SDA
  └────────────┘                  GP8 │ 11              30│ RUN
                                  GP9 │ 12 ◄── pin 10    │
        all 10 header pins → GP0..GP9 │ 13 (GND, unused) │       ┌──────────┐
        (no hard ground used)         │ ...              │       │ SBC-OLED01│
                                      └──────────────────┘       │  128x64   │
                                                                 └──────────┘
```

On the **left**, reading top to bottom, both columns only ever move *downward*
(GP0…GP9), so the DUT jumpers never cross. The Pico's hard GND at physical 13 is
now **unused** by the DUT. On the **right**, the four OLED wires land in the
pin 31–36 cluster.

Each breadboard row (the 5 holes a–e on one side of the channel) is one electrical
node, so "plug DUT pin into a hole in the same row as the jumper's other end."

---

## 5. Step-by-step wiring

1. **Power off** — leave the Pico unplugged from USB while you wire.
2. Seat the Pico across the center channel so its left-edge pins are accessible.
3. Insert the DUT 10-pin header into the breadboard, parallel to the Pico.
4. Wire the header **straight down the left edge**: DUT pin *i* → GP(i−1).
   That is pins 1→GP0, 2→GP1, 3→GP2, 4→GP3, 5→GP4, 6→GP5, 7→GP6, 8→GP7, 9→GP8,
   **10→GP9 (physical pin 12)** — *not* the GND pin. No header pin touches the
   Pico's hard ground.
5. Wire the **OLED** on the right edge (match its silkscreen labels):
   VCC→3V3 (pin 36), GND→GND (pin 33), SCL→GP27 (pin 32), SDA→GP26 (pin 31).
6. Double-check against the tables — pin 10 going to GP9 (not GND), and swapped
   SDA/SCL, are the two easiest mistakes.

> **About series/pull-up resistors:** the NAND-only build suggested optional 1 kΩ
> series resistors on the drive lines. **Leave them off for the multi-board rig** —
> on the RS board the R/S lines must be pulled close to 0 V to flip a latch, and a
> series resistor against the board's pull-up would keep them too high. The Pico's
> internal pull-ups (NAND/XNOR outputs) and the boards' own pull-ups (RS nodes) are
> all that's needed. All three boards are very low power, so direct drive is fine.

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

> **Forcing a board type.** `main.py` auto-detects by default. If you'd rather
> skip detection (e.g. to avoid the brief NAND/RS probe activity on a partly-built
> board), set `BOARD = "nand"`, `"rs"`, or `"xnor"` at the top of `main.py`
> instead of `"auto"`. With your half-populated XNOR board, `BOARD = "xnor"` jumps
> straight to the XNOR report.

> Prefer C/C++ SDK or rshell/ampy? Same pin map applies — DUT pin *i* → GP(i−1),
> GND/VCC synthesised by driving the relevant GPIO; OLED on I²C1 (GP26 SDA, GP27
> SCL) at address 0x3C.

---

## 7. Run and read the result

- With `main.py` on the Pico, it runs automatically at power-up, **auto-detects
  the board, and re-tests every couple of seconds** (so you can hot-swap boards).
- Detection, in order: run the NAND test — if **any gate** behaves like a NAND
  it's NAND. Else run the RS test — if **any latch** works it's RS. Else fall back
  to **XNOR**, which is tested and reported regardless of the result.
- Open the serial console (Thonny REPL, or `screen`/`minicom`/PuTTY at the Pico's
  USB serial port) to see the full report. NAND board:

```
=== PCB tester ===
Board: 3x open-collector NAND
  G1 ~(A&B)   PASS
     a=0 b=0 exp=1 got=1 ok
     a=1 b=1 exp=0 got=0 ok
  G2 ~(C&D)   PASS
  G3 ~(E&F)   PASS
  RESULT: ALL GATES PASS
```

  RS board:

```
=== PCB tester ===
No NAND gate behaved correctly -> trying RS flip-flop
Board: 2x RS flip-flop
  FF1  PASS   (cycle 3)
     RESET got R0 S1 (exp R0 S1)
     SET   got R1 S0 (exp R1 S0)
  FF2  PASS   (cycle 3)
     ...
  RESULT: ALL FLIPFLOPS PASS
```

  XNOR board (here the second gate isn't built yet, so it fails — which is fine,
  XNOR is the fallback and is reported anyway):

```
=== PCB tester ===
No NAND gate behaved correctly -> trying RS flip-flop
No RS flip-flop worked either -> testing as XNOR
Board: 2x XNOR
  X1 ~(A^B)   PASS
     a=0 b=0 exp=1 got=1 ok
     a=0 b=1 exp=0 got=0 ok
     a=1 b=0 exp=0 got=0 ok
     a=1 b=1 exp=1 got=1 ok
  X2 ~(C^D)   FAIL
     a=0 b=0 exp=1 got=1 ok
     a=0 b=1 exp=0 got=1 <- MISMATCH
     ...
  RESULT: FAULT DETECTED
```

- **OLED display**: shows the live verdict at a glance — no laptop needed. It
  **rotates through pages**: a summary (~3.5 s), then one detail page for *each*
  failing unit (~8 s each, since they carry more to read), then back to the summary.

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

  For the **RS board** the pages follow the same shape — a summary, then a detail
  page per failing flip-flop:

  ```
  PAGE 1 — summary        PAGE 2 — detail (per failing FF)
  2x RS FLIPFLOP          FF2 FAIL
  FF1 PASS                RESET exp R0 S1
  FF2 FAIL                 got R0 S1 ok
                          SET   exp R1 S0
  ** FAULT **              got R0 S1 BAD   <- did not flip / did not hold
  (screen inverts)        (cycle 0)
  ```

  `RESET` is "after pulling R low" (expect R=0, S=1); `SET` is "after pulling S
  low" (expect R=1, S=0). A `BAD` on SET like the one above means the latch didn't
  switch to (or hold) the set state — a stuck node, a missing pull-up, or a broken
  cross-coupling.

  The **XNOR board** uses the same gate layout as the NAND board — a summary
  (`2x XNOR TESTER`, `X1 ~(A^B)` / `X2 ~(C^D)`) plus a 4-row truth-table detail
  page per failing gate, where the expected column is `1` iff the inputs are equal.
  On your current board X1 passes and X2 (not built yet) shows up `FAIL`.
- **Onboard LED**: steady ON = everything passes; fast blink = at least one fault.
  A redundant at-a-glance indicator that works even if the OLED is unplugged.
- The **serial console** prints the full per-gate / per-flip-flop log each run; the
  OLED detail pages mirror it for the failing units without needing a laptop.

> Tune the rotation speed near the top of `main.py`: `PAGE_MS` is the dwell for
> summary/overview pages (default 3500 ms) and `DETAIL_MS` is the longer dwell for
> failure-detail pages, which carry more to read (default 8000 ms).

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
| A fully-dead NAND/RS board falls through to an "XNOR" report | Auto-detect picks the **first** type with a working unit; if none work it lands on XNOR (the fallback). Force `BOARD` to the intended type to see that board's detail |
| RS: both nodes read the same (both 0 or both 1) | VCC (pin 1→GP0) or GND (pin 6→GP5) not reaching the board; or the latch's cross-coupling is broken / a node shorted |
| RS: state doesn't hold (RESET ok but next read flips) | Weak/missing board pull-up on that node, or the holding transistor is open — `hold` check catches this |
| RS: never flips at all | pin 10 still wired to the Pico's hard GND (S2 grounded), or R/S can't be pulled low — remove any series resistors |
| RS: FF1 works, FF2 doesn't (or vice-versa) | Fault localised to that latch's R/S pair — check pins 8/10 (FF2) or 2/4 (FF1) and their components |
| XNOR: a gate reads inverted (`0↔1` everywhere) | The gate is wired/built as **XOR**, not XNOR — flip the `exp` line (see §1) or fix the board |
| XNOR: output stuck regardless of inputs | VCC (pin 6→GP5) or GND (pin 5→GP4) not reaching that gate, or its output shorted; X1 uses pins 1/2/3, X2 uses pins 8/9/10 |

All three tests isolate faults to a single unit — a gate + input combination
(NAND/XNOR) or FF1/FF2 with RESET vs SET (RS) — so a `BAD` line points you straight
at the offending net or component.

---

## 9. How the test works (theory)

### NAND board
For each gate, for each of the four input combinations:
1. Park all six inputs LOW.
2. Drive that gate's two inputs to the test combination at 3.3 V.
3. Wait ~300 µs for the open-collector node to settle through the pull-up.
4. Sample the output 5× and majority-vote.
5. Compare against `expected = NOT(a AND b)`.

A logic "1" read means the output transistor is **off** and the pull-up won the
node; a "0" means the output is actively pulling to GND. That's exactly the
open-collector NAND behaviour, so a correct board passes all 12 checks
(3 gates × 4 rows). The firmware drives only one gate's inputs at a time (others
parked LOW), so a fault is isolated to a specific gate and input combination.

### RS flip-flop board
First power the board: drive **VCC (GP0) high** and **GND (GP5) low**, leave all
R/S nodes as high-impedance inputs (the board's own pull-ups define the highs).
Then, for each latch, repeat for several cycles:
1. **RESET** — drive R low briefly, release to high-Z. Read: expect **R=0, S=1**.
2. **Hold** — read R/S again without touching anything: must still be R=0, S=1.
3. **SET** — drive S low briefly, release. Read: expect **R=1, S=0**.
4. **Hold** — read again: must still be R=1, S=0.

Pulling one node to ground turns off the transistor it feeds, letting the partner
node rise; the risen node then turns *on* the transistor that keeps the first node
low — so the latch **holds its state** after you release the line. The two reads
per state are what catch a latch that switches but won't hold. The two flip-flops
use disjoint pins, so a fault is isolated to FF1 or FF2.

### XNOR board
Power it (drive **VCC (GP5) high**, **GND (GP4) low**), then for each gate walk
the four input combinations: drive the two inputs, wait, read the output, and
compare against **`expected = (A == B)`** (XNOR is 1 when the inputs agree). The
output is read with a pull-up — harmless for a push-pull output and necessary if
it turns out to be open-collector. The two gates use disjoint pins, so a fault
localises to X1 or X2 (handy right now, with X2 not yet built). It's the
detection fallback because, unlike NAND (an all-1s output until both inputs are
high) and RS (a latch you can flip), a correct XNOR has no signature the other
two tests would mistake for their own — so "neither NAND nor RS" ⇒ treat as XNOR.

### Why all ten pins go to GPIOs
A GPIO driven low is a perfectly good ground for a board that sinks well under a
milliamp, and a GPIO driven high is a good enough 3.3 V rail for a board that
draws almost nothing — which all three of these are. Synthesising the supplies in
firmware (instead of wiring a fixed ground) is what lets the *same* ten jumpers
serve boards whose VCC/GND pins sit in different header positions.

---

## 10. Adapting to other boards

This rig is a general pattern. To add a third board:
- Keep the uniform wiring (DUT pin *i* → GP(i−1)); just decide each pin's role in
  firmware. Use `drive(gp, 1/0)` for VCC/GND or to apply inputs, `release(gp)` /
  `release(gp, Pin.PULL_UP)` for high-Z reads, and `read_stable(gp)` to sample.
- Write a `xxx_test()` returning `(name, ok, detail)` per unit, plus `xxx_pages()`
  and `print_xxx()`, then slot it into `run_once()` (and the auto-detect chain).
- For push-pull (totem-pole) outputs, read with plain `release(gp)` (no pull-up).
- For a board needing more current than a GPIO can give, feed VCC from the Pico's
  **3V3** pin (pin 36, ~300 mA) instead of a GPIO, sharing GND.
- Auto-detect tries each board's test in order and stops at the first that shows a
  working unit (≥1 NAND gate ⇒ NAND; else ≥1 RS latch ⇒ RS; else XNOR fallback).
  Put the board with no distinguishing "pass signature" last, as the fallback.

---

## 11. License

This project is released under the [MIT License](LICENSE).

`ssd1306.py` is the canonical OLED driver from the
[MicroPython project](https://github.com/micropython/micropython-lib), also under
the MIT License. It is bundled here for convenience so the Pico ends up with both
required files; all credit for it goes to the MicroPython authors.
