# Robot Buddy — Electrical Design Calculations

> Worked numbers for robot-buddy-reflex, checked **before the v2 layout**. Written 2026-08-06,
> in the style of `robot-scout/docs/electrical-design-calcs.md`.
>
> **Why arithmetic and not SPICE.** Scout's audit found simulation would have caught ~5 of its
> 25 defects and **none of the blockers** — v1 failed on geometry, connectivity and process, and
> a simulator will happily pass a board with no traces on it. The boring arithmetic below is
> cheap and checkable by inspection.
>
> Every number states its assumptions. Unverified inputs are listed explicitly at the end —
> do not promote one to a fact without measuring it.
>
> Source: `robot-buddy-reflex.kicad_pcb` after the E1 fix, net classes from `.kicad_pro`.

---

## 0. Capacitance inventory — buddy is *not* short

Starting here because scout's boards were badly under-provisioned (mcu and gimbal had one
100 nF each; power had **zero** capacitors). Buddy is the opposite case.

| Ref | Value | Net | Role |
|-----|-------|-----|------|
| C3 | 1000 µF | `+BATT` | bulk on battery/motor node |
| C4 | 100 nF | `+BATT` | HF bypass on battery node |
| C6 | 100 µF | `+5V` | bulk on 5 V arriving over J9 cable |
| C7 | 100 nF | `+5V` | HF bypass, 5 V |
| C5 | 100 nF | `+3V3` | HF bypass, 3V3 |
| C1 | 100 nF | `/ESTOP` | debounce |
| C2 | 100 nF | `/BAT_SENSE` | ADC charge reservoir — **load-bearing, see §3** |

Against the four checks:

- ✅ **100 nF per active device.** U1 (module, has its own onboard decoupling), U2 (breakout
  carries 2× 0402 + an EIA3528 tantalum at the chip — confirmed in the SparkFun Eagle `.brd`),
  U3 has C7 on its `+5V`. Every active rail has a 100 nF.
- ✅ **Bulk on every rail input arriving over a cable.** `+5V` enters on J9 → C6 100 µF.
  `+BATT` enters on J8 → C3 1000 µF. Both exceed the 10–22 µF guideline.
- ✅ **Input bulk on the battery node — and it is what makes hot-plug safe.** See §0a.
- 🔴 **No bulk on `+3V3`.** It is derived from the ESP32-S3-Zero's *onboard LDO* and leaves the
  board over the J5 Qwiic cable, but carries only C5 100 nF. **Add 10 µF.** This is the one
  genuine capacitance gap, and it gets worse in v2 when the I²C expander (and possibly an ADC)
  become on-board 3V3 loads.

### 0a. Hot-plug ringing on `+BATT` — quantified

Lead inductance rings against the input capacitance on connect. Second-order response,
`Z₀ = √(L/C)`, `ζ = R_series / 2Z₀`; `ζ ≥ 1` means no overshoot at all.

**Assumption:** 0.3–0.5 µH lead inductance, 1000 µF electrolytic ESR ≈ 0.2 Ω, 8.4 V pack.

| Case | L | Z₀ | ζ | f_ring | Result |
|------|---|-----|---|--------|--------|
| Buddy, C3 1000 µF | 0.3 µH | 0.0173 Ω | **5.77** | 9.2 kHz | overdamped — no ring |
| Buddy, C3 1000 µF | 0.5 µH | 0.0224 Ω | **4.47** | 7.1 kHz | overdamped — no ring |
| *No bulk, 1 µF ceramic only* | 0.3 µH | 0.548 Ω | 0.046 | 291 kHz | **peak ≈ 15.7 V** |
| *No bulk, 1 µF ceramic only* | 0.5 µH | 0.707 Ω | 0.035 | 225 kHz | **peak ≈ 15.9 V** |

✅ **Buddy is safe** — C3's ESR alone overdamps the loop by 4–6×.

The bottom two rows are the scout failure mode, and they explain why it matters: a ~15.8 V
peak from an 8.4 V pack exceeds the **TB6612's 15 V absolute maximum**. The Pololu modules
survive it; a 6–13.5 V motor driver does not. The 1000 µF is not optional decoration.

### 0b. 🟡 Capacitor *placement* is the real capacitance defect

Values are right; distances are not. Measured pad-to-pad on the current layout:

| Cap | Serves | Distance |
|-----|--------|----------|
| C3 1000 µF | U2 `VM` (pad 9) | **31.8 mm** |
| C3 1000 µF | J8 `+BATT` entry | **53.7 mm** |
| C4 100 nF | U2 `VM` | 30.9 mm |
| C6 100 µF | J9 `+5V` entry | 39.9 mm |
| C7 100 nF | J9 `+5V` entry | 35.9 mm |
| C7 100 nF | U3 `+5V` | 7.4 mm |
| C5 100 nF | U1 `+3V3` | 26.9 mm |

`docs/power.md:34` relies on C3 specifically — *"a 1000 µF bulk cap on VM input absorbs
motor-surge sag so the rail stays above the 4.5 V floor during direction flips."* At 31.8 mm
it is not on the VM input in any electrical sense.

**Honest magnitude, though:** 0.5 mm trace, 1 oz, 31.8 mm → R ≈ 31 mΩ and L ≈ 32 nH. A 1.5 A
step gives ~47 mV IR drop and ~48 mV of L·di/dt at 1 A/µs. That is *not* what breaks a 4.5 V
floor, and the breakout's own onboard caps cover the high-frequency work. So this is 🟡
sloppy-but-survivable, not a blocker — worth fixing in the v2 placement, not worth a respin
on its own.

⚠ **The E1 fix made this worse.** Pad 16 used to be (wrongly) `+BATT` and sat 15.2 mm from C3.
Now pad 9 is the only VM pin, at 31.8 mm. **The v2 layout must place C3 next to pad 9.**

---

## 1. Trace current and temperature rise

**Method:** IPC-2221 external-conductor curve, `I = 0.048·ΔT^0.44·A^0.725`, A in mil².
1 oz = 1.4 mil, 2 oz = 2.8 mil.

**Assumption — 1 oz outer copper.** Not specified in the board stackup; JLC's 4-layer default
is 1 oz outer. Stated as an assumption, but see the finding below.

Net classes (from `.kicad_pro`): Default 0.25 mm, Power 0.5 mm (`+5V`, `+BATT`, `+3V3`, `GND`),
Motor 0.8 mm (`/AO1`, `/AO2`, `/BO1`, `/BO2`).

| Class | Width | Rating @ 1 oz, 30 °C | Rating @ 2 oz, 30 °C |
|-------|-------|----------------------|----------------------|
| Default | 0.25 mm | 1.44 A | 2.37 A |
| Power | 0.50 mm | **2.37 A** | 3.92 A |
| Motor | 0.80 mm | 3.34 A | 5.52 A |

Actual loads at 1 oz — the worst-case column:

| Net | Width | Current | ΔT |
|-----|-------|---------|-----|
| `+BATT`/VM continuous | 0.5 mm | 0.30 A | 0.3 °C |
| `+BATT`/VM peak (direction flip) | 0.5 mm | 1.50 A | **10.6 °C** |
| Motor output continuous | 0.8 mm | 0.15 A | 0.0 °C |
| Motor output stall | 0.8 mm | 0.70 A | 0.9 °C |
| `+5V` continuous | 0.5 mm | ~0.55 A | 1.1 °C |
| `+5V` with 8 NeoPixels full white | 0.5 mm | ~1.03 A | 4.5 °C |

✅ **Everything passes comfortably, even at 1 oz.** Worst case is a 10.6 °C rise on a
2.37 A-rated conductor carrying 1.5 A.

Worth contrasting with scout: there the copper weight *swung the verdict* (15 A on 2 oz = 44 °C,
on 1 oz = 138 °C and destructive). Here buddy's currents are an order of magnitude lower, so
the unknown is harmless. **Still specify 1 oz explicitly on the v2 order** — but this is
documentation hygiene, not a risk.

---

## 1a. Copper weight — **DECIDED 2026-08-06: 1 oz outer / 0.5 oz inner, ENIG**

Now declared in the board stackup by `layout_pcb.py`, so it is a decision rather than an
assumption. §1 above is the **v1** analysis and is stale: it sizes `+BATT` and NeoPixels,
which no longer exist, and quotes a 0.8 mm Motor class that is now 0.4 mm.

Scout used 2 oz because there the copper weight *swung the verdict* — 15 A on 1 oz
reached 138 °C. Buddy is a different board and inheriting that number would be cargo
cult, so it was re-derived from buddy's own loads.

### What each conductor actually carries (v2)

IPC-2221, `I = k·ΔT^0.44·A^0.725`, k = 0.048 external / 0.024 internal, ΔT = 30 °C.
All outer routing is 0.25 mm (Default) or 0.40 mm (Rail / Power / Motor).

| Conductor | Width | Peak | Rating @1 oz | ΔT at peak | Margin |
|---|---|---|---|---|---|
| Motor output `/AO1` etc | 0.40 mm | 0.75 A | 1.99 A | **3.3 °C** | 2.6× |
| `+5V` surface → U1 | 0.40 mm | 0.25 A | 1.99 A | 0.3 °C | 7.9× |
| `+5V` surface → decoupling | 0.40 mm | 0.05 A | 1.99 A | 0.0 °C | 39× |
| `+3V3` (expander + IMU) | 0.40 mm | 0.01 A | 1.99 A | 0.0 °C | 199× |

The worst outer conductor on the board runs **3.3 °C hot**. It is not close.

### The 1.5 A motor-flip current is shared, and the plane takes ~98 % of it

⚠ **An earlier draft of this section claimed the motor current "never touches outer
copper". That was wrong**, and `trace_path.py` is what caught it — the tool that exists
precisely because "confirmed on 2 oz" claims in this project kept turning out to be about
copper *near* a pad rather than copper *on the path*. Walking J9.1 → U2.9 finds a
complete outer-copper route: **~92 mm of 0.40 mm track across B.Cu and F.Cu**.

Both paths exist and they are in **parallel**, because `route_pcb.py` strips the inner
layers from the DSN — freerouting cannot see the plane, so it routes `+5V` on the outer
layers as though there were none, while KiCad's zone connects the same pads underneath.

| Path | Resistance |
|---|---|
| Surface: 92 mm of 0.40 mm at 1 oz | **113 mΩ** |
| In2.Cu plane: ~2.7 squares at 0.5 oz (0.99 mΩ/sq) | **2.7 mΩ** |

So the plane carries **97.7 %** and the surface run **2.3 %** — at a 1.5 A flip the outer
copper sees about **35 mA**. The conclusion survives; the reasoning had to be corrected.

**And it holds even if the plane is discounted entirely**, which is the honest way to
size a fallback:

| Case | vs 1.99 A rating | ΔT |
|---|---|---|
| Continuous 0.30 A | 6.6× | 0.4 °C |
| Direction flip 1.50 A | **1.3×** | 15.8 °C |

1.3× is thin as a steady-state number, but a direction flip lasts milliseconds against a
trace thermal time constant of seconds, and the continuous case is 6.6×. Verified paths:

| Path | Weakest link (1 oz) | Peak | Margin |
|---|---|---|---|
| J9.1 → U2.9 (VM feed) | 0.40 mm, 1.99 A | 1.50 A | 1.3× |
| U2.12 → J1.1 (motor output) | 0.40 mm, 1.99 A | 0.75 A | 2.6× |
| U2.9 → C3.1 (bulk) | 0.40 mm, 1.99 A | 0.15 A RMS | 13× |

### Every +5V node reaches the plane directly

This is what makes the parallel path above work at all:

| `+5V` node | Pad | Path |
|---|---|---|
| J9.1 (power in) | PTH | barrel straight onto the In2.Cu plane |
| U2.9 (VM) | PTH | barrel straight off the plane |
| C3.1 (1000 µF bulk) | PTH | barrel onto the plane |
| J1.3 / J2.3 / J6.1 | PTH | barrel onto the plane |

All three zones use `ZONE_CONNECTION_FULL`, so those are solid connections, not thermal
spokes. Capacity of that path, deliberately pessimistic:

| Element | Capacity @30 °C |
|---|---|
| In2.Cu plane, assuming only a **10 mm strip** participates, at 0.5 oz | **6.2 A** |
| One 1.0 mm PTH barrel, 25 µm plating | **7.0 A** |
| One 1.7 mm PTH barrel (J9), 25 µm plating | **10.2 A** |

Against a 1.8 A peak (0.25 A logic + 1.5 A direction flip) and a ~5 A source.

### 2 oz would have cost margin, not bought it

The binding constraint on this board is **spacing, not current**. It routes at 0.20 mm
clearance and 0.25 mm minimum track:

| | JLC min trace/space, 4-layer | Our margin |
|---|---|---|
| **1 oz outer** | 0.0889 mm | **2.25× on clearance**, 2.8× on track |
| 2 oz outer | 0.20 mm | **1.0× — exactly on the limit** |

So 2 oz would put every clearance in the design on the fab's stated minimum, in exchange
for headroom on conductors already running 3 °C warm. 1 oz is both the cheaper and the
*safer* choice here.

### Consequence for the gate

`check_pcb_ampacity.py` had a hardcoded 2.0 oz default and never looked at the board —
so it reported ~40 % more ampacity than a 1 oz board has, and could not tell a declared
2 oz board from one that declared nothing. It now reads the stackup, prints the source
(`[board stackup]` vs `[ASSUMED — board declares no stackup]`), and warns on stderr when
it has to guess.

---

## 2. 🔴 Protection coordination — buddy has no overcurrent device at all

The rule: **fuse rating < conductor rating < connector rating.** Buddy has no fuse, so the
chain reads:

| Element | Rating |
|---------|--------|
| Source (UPS HAT 5 V / 5 A) | **~5 A available** |
| J8 / J9 connector (JST-XH) | 3 A per contact |
| `+BATT` / `+5V` trace (0.5 mm, 1 oz) | **2.37 A** |
| Overcurrent device | **none** |

The ordering is **inverted**: source capacity (5 A) > connector (3 A) > conductor (2.37 A),
with nothing to interrupt a fault. A short downstream of J8 draws whatever the HAT delivers,
and the trace is the weakest element in the chain — so the copper is the fuse.

This is buddy's analogue of scout's 20 A fuse on a 12.6 A trace. Different mechanism (no
device rather than a mis-sized one), identical coordination failure.

The 18650 protection circuits and the HAT's cutoff protect the **pack**. They do not protect
buddy's copper, and should not be counted as this board's overcurrent protection.

**Fix for v2 — add a fuse on each incoming rail:**

- [ ] `+BATT` (J8): **2 A** slow-blow. Motors peak 1.5 A, so 2 A clears the working load.
      Coordination: 2 A fuse < 2.37 A trace < 3 A connector ✅
- [ ] `+5V` (J9): **2 A** slow-blow. Load 0.55–1.03 A. Same coordination ✅
- [ ] If a larger fuse is ever wanted, widen first: 1.0 mm at 1 oz = 3.92 A, which would
      support a 3 A fuse against the 3 A connector.

---

## 3. Dividers — actual voltage into every input

### 3a. `/BAT_SENSE` → U1 pad 4 (ADC)

R8 = 100 kΩ (`+BATT`→node), R9 = 47 kΩ (node→GND). Ratio **0.31973**, Z_out **32.0 kΩ**.

**Assumption:** ESP32-S3 ADC at 12 dB attenuation, usable full scale ≈ 3.1 V (datasheet
typical), absolute maximum on the pin 3.6 V.

| `+BATT` | ADC sees | Margin to 3.1 V |
|---------|----------|-----------------|
| 5.0 V | 1.599 V | +1.501 V |
| 7.4 V (2S nominal) | 2.366 V | +0.734 V |
| 8.4 V (2S full) | **2.686 V** | **+0.414 V** ✅ |
| 12.6 V (3S) | 4.029 V | **−0.929 V** 🔴 destructive |

- ✅ Safe and reasonably scaled for a 2S pack — 87 % of usable range at full charge.
- 🔴 **2S-only by construction.** A 3S pack puts 4.03 V on the pin, over the 3.6 V absolute
  maximum. If the pack ever changes, this divider must change with it. Record it next to the
  battery spec, not only here.
- 🟡 **Z_out is 32 kΩ against an ESP32 SAR ADC that wants ≤ 10 kΩ.** What rescues it is
  **C2 (100 nF)** acting as a charge reservoir for the sampling capacitor. C2 is load-bearing —
  do not "clean it up" in v2. Alternatively drop to 10 k/4.7 k for a 3.2 kΩ source.
- ⚠ **The whole circuit's purpose is unresolved.** If `+BATT` is really the 5 V rail (see the
  topology contradiction in §6), this reads 1.599 V and tells you nothing about pack state of
  charge. Resolve A3 in the defect register before keeping it.

### 3b. `/ECHO_DIV` → U1 pad 5 (digital GPIO)

R5 = 10 kΩ (`/ECHO_IN`→mid), R6 = 20 kΩ (mid→GND), R7 = 100 Ω series to the pin.
Ratio **0.6667**, Z_out 6.67 kΩ.

**Assumption:** HC-SR04 echo output swings to its 5 V supply; 5.25 V worst case.
ESP32-S3 V_IH = 0.75 × 3.3 = 2.475 V; absolute maximum 3.6 V.

| HC-SR04 supply | Pin sees | Margin to 3.6 V absmax |
|----------------|----------|------------------------|
| 5.00 V | 3.333 V | +0.267 V |
| 5.25 V | **3.500 V** | **+0.100 V** 🟡 |

- 🟡 **Only 100 mV of absolute-maximum margin** at a high-side 5 V supply. Legal, but there is
  no reason to run this tight when the logic margin is enormous — 3.33 V against a 2.475 V
  threshold is 860 mV of headroom we are not using.
- [ ] **Change R6 to 15 kΩ** → 3.000 V at 5.0 V, 3.150 V at 5.25 V. V_IH margin still 525 mV,
      and absolute-max margin improves from 0.100 V to 0.450 V.
- ✅ R7 100 Ω in series is good practice — limits current into the pin's clamp diode if the
  input is ever driven above rail.
- ✅ Timing is fine: 6.67 kΩ against ~10 pF of stray is a 67 ns time constant, negligible
  against HC-SR04 echo pulses of 150 µs–25 ms.

---

## 4. Rail budgets

### 4a. 5 V rail — 🟡 tight, and NeoPixel count decides it

**Source:** UPS HAT (B), 5 V at 5 A. Everything downstream shares it.

| Load | Continuous | Peak |
|------|-----------|------|
| Pi 5 | 2.0–2.5 A | 2.5 A |
| ESP32-face + TFT | ~0.5 A | ~0.5 A |
| ESP32-reflex (U1) | ~0.25 A | ~0.25 A |
| Motors via TB6612 VM | 0.30 A | **1.50 A** (direction flip) |
| NeoPixels (N × 60 mA full white) | **unknown** | **unknown** |
| **Subtotal without NeoPixels** | **~3.55 A** | **~4.75 A** |

- Headroom before NeoPixels: **~0.25 A at peak.**
- 4 pixels at full white (0.24 A) → 4.99 A — exactly at the limit.
- 8 pixels at full white (0.48 A) → **5.23 A, over budget.**

The coincidence required is real but not exotic: a direction flip while the Pi bursts and the
NeoPixels are at full white. **Either cap NeoPixel brightness in firmware, keep N ≤ 4, or
accept the transient.** Whichever is chosen, write it down — this is a design constraint, not
an implementation detail.

### 4b. 3V3 rail — ✅ trivially within budget

Derived from the ESP32-S3-Zero's **onboard LDO** (U1 pad 3).

| Load | Current |
|------|---------|
| U2 `VCC` (TB6612 logic) | ~1.5 mA |
| BMI270 over J5 Qwiic | ~0.7 mA |
| R4 10 kΩ pull-up (E-stop closed) | 0.33 mA |
| **Total** | **~2.5 mA** |

✅ Any LDO handles this. Flagged only because v2 adds an I²C expander and possibly an ADC to
this rail — still small, but re-check against the module's actual LDO rating (unverified).

---

## 5. 🔴 I²C — the board has no pull-ups at all

`t_r ≈ 0.8473 · R · C`; limits are 1000 ns at 100 kHz and 300 ns at 400 kHz.

**There are no pull-up resistors on `/SDA` or `/SCL`.** Confirmed by enumerating all eleven
resistors — R1/R2/R3 are motor-input pull-downs, R4 is the E-stop pull-up, R5/R6/R7 the echo
divider, R8/R9 the battery divider, R10 the LED, R11 the NeoPixel series. None touch I²C.

The bus works today **only because the external SparkFun Qwiic BMI270 breakout carries its
own** (assumed 2.2 kΩ).

**Assumption:** ~55 pF bus capacitance (short board traces + J5 + ~100 mm Qwiic cable + device
pin capacitance); 100 pF for a longer cable.

| Pull-up | 55 pF | 100 pF | Verdict |
|---------|-------|--------|---------|
| 2.2 kΩ (assumed Qwiic device) | 103 ns | 186 ns | ✅ passes even 400 kHz |
| 4.7 kΩ | 219 ns | 398 ns | ✅ 400 kHz / ✅ 100 kHz |
| 10 kΩ | 466 ns | 847 ns | ✅ 100 kHz only |

**Findings:**

- 🟡 **Today:** functional, but the bus depends entirely on a cable-attached breakout. Unplug
  J5, or plug in a Qwiic device whose pull-ups are cut, and I²C stops.
- 🔴 **For v2 this becomes a blocker.** The A1 architecture change puts an I²C GPIO expander
  (carrying all four motor-direction pins) **on the board**. The bus must then work with J5
  empty — and with no pull-ups it will not. Motor direction control would depend on an
  external sensor breakout being plugged in.
- [ ] **Add 4.7 kΩ pull-ups to `+3V3` on-board for v2.** Alone: 219 ns ✅. In parallel with a
      2.2 kΩ Qwiic device: 1.5 kΩ → 70 ns ✅, sink current 3.3 V / 1.5 kΩ = **2.2 mA**, inside
      the 3 mA I²C spec ✅.

---

## 6. LED series resistor — ✅ correct, and for a non-obvious reason

R10 = 330 Ω from **`+5V`** to `/LED_A`; the LED itself is off-board on J10 to GND.

| LED | V_f | Current | P(R10) |
|-----|-----|---------|--------|
| Red | 2.0 V | 9.09 mA | 27.3 mW |
| Green | 2.2 V | 8.48 mA | 23.8 mW |
| Blue / white | 3.2 V | 5.45 mA | 9.8 mW |
| High-V_f white | 3.4 V | 4.85 mA | 7.8 mW |

✅ **Works for every LED colour**, because it is fed from 5 V rather than 3.3 V. The same
330 Ω from `+3V3` with a 3.2 V blue would pass **0.30 mA — invisible**. Buddy avoids that trap
by accident of rail choice; worth keeping deliberate in v2.

✅ R10 dissipation 27 mW worst case, against a 0402's 63–100 mW rating.

V_f is unverified (the LED is an off-board part on a cable) but it does not change the verdict.

---

## 7a. SUPERSEDED 2026-08-06 — topology resolved, NeoPixels cut

Recorded as a supersession rather than a rewrite, so the reasoning above stays auditable.

**Correction to §1 — I costed the wrong trace widths.** §1 used the net-class widths from
`.kicad_pro` (Power 0.5 mm, Motor 0.8 mm). The router overrides those after SES import:
`route_pcb.py:35` sets `POWER_W = 0.40 mm` **and** `MOTOR_W = 0.40 mm`. Real ratings at
1 oz are therefore **2.02 A**, not 2.37/3.34 A.

**Topology (unverified input #1) is resolved:** buddy is powered from the Pi HAT alone; the
2S pack tap is gone. `+BATT` is eliminated, `/BAT_SENSE` deleted, TB6612 `VM` fed from `+5V`.

| Section | Was | Now |
|---|---|---|
| §1 widths | 0.5 / 0.8 mm | **0.40 mm both** → 2.02 A at 1 oz |
| §1 loads | `+BATT` and `+5V` separate | one rail: 1.5 A motors + 0.25 A logic = **1.75 A peak**, 87 % of rating, ΔT ≈ 22 °C |
| §2 fuses | 2 A on `+BATT` *and* `+5V` | **one 2 A slow-blow on `+5V`.** Rule restated as *fuse < min(conductor, connector)*: 2 A < 3.34 A (at the widened 0.8 mm) and 2 A < 3 A JST-XH ✅ |
| §3a `/BAT_SENSE` | 100 k/47 k divider, 2S-only | **deleted** — R8, R9, C2 removed. The 32 kΩ-source and 3S-destructive notes are moot. |
| §4a 5 V budget | 4.75 A + NeoPixels, tight | **4.75 A, NeoPixels cut.** ~0.25 A headroom. |
| §0a hot-plug | 1000 µF on `+BATT`, ζ ≈ 4.5–5.8 | C3 moves to `+5V` alongside C6; still heavily overdamped, no ring ✅ |
| §6 LED | — | unchanged; J10/R10 is the separate always-on power LED, not the NeoPixel |

**New finding — §1's width was justified by a premise that later changed.** `POWER_W` was
narrowed 0.50 → 0.40 mm "to clear NeoPixel cluster; adequate for <500 mA 5V rail". Motors are
now on `+5V`, so the <500 mA premise is void — and the NeoPixel cluster it was dodging has
been deleted, so the original reason is void too. **Widen to 0.8 mm** (3.34 A, ΔT ≈ 7 °C).
Same defect class as scout's fuse-vs-trace: a number correct when written, never re-checked
when its assumption moved.

**🔴 New risk introduced by the topology change:** `VM` now sits 0.5 V above the TB6612's
4.5 V floor. C3 1000 µF must be placed **at pad 9** — §0b's placement finding is promoted
from 🟡 to 🔴.

---

## 7. UNVERIFIED INPUTS

Nothing below has been measured. Each is an assumption this document rests on.

| # | Input | Assumed | Impact if wrong | Severity |
|---|-------|---------|-----------------|----------|
| 1 | ~~**`+BATT` source**~~ **RESOLVED 2026-08-06 — Pi HAT 5 V only, no pack tap. `+BATT` eliminated.** | ~~2S pack, 7.4–8.4 V~~ | **Contradiction between the board and `docs/power.md:9-17`**, which specifies a *single-rail 5 V* topology feeding "TB6612 VM" from the HAT's 5 V. The board implements a separate `+BATT` input (J8), a pack-scaled divider, and a `+BATT` inner plane. If 5 V is correct, §3a measures the wrong thing and VM sits 0.5 V above its 4.5 V floor. | 🔴 blocker — resolve with A3 |
| 2 | Outer copper weight | 1 oz | None here — every trace passes at 1 oz. Specify on the v2 order for hygiene. | 🟢 low |
| 3 | ~~NeoPixel count on J11~~ **RESOLVED — NeoPixels cut entirely; J11/U3/R11 deleted.** (The board had documented an 8×8 = 64-pixel matrix, which no rail here could feed.) | ~~8~~ | Decides whether the 5 V rail peak exceeds the HAT's 5 A (§4a). At N ≤ 4 it fits. | 🟡 medium |
| 4 | Qwiic BMI270 pull-up value | 2.2 kΩ | Sole reason I²C works today (§5). At 10 kΩ, 400 kHz is unavailable. | 🟡 medium |
| 5 | UPS HAT short-circuit behaviour | sources up to ~5 A | Determines whether the unfused traces are genuinely at risk (§2). If it folds back hard, the exposure shrinks — but the coordination is still inverted. | 🟡 medium |
| 6 | ESP32-S3-Zero onboard LDO rating | ≥ 100 mA | Irrelevant at today's 2.5 mA; matters once v2 adds expander + ADC. | 🟢 low |
| 7 | HC-SR04 supply | 5.0 V nom, 5.25 V max | Sets the 100 mV absolute-max margin in §3b. A 5.5 V supply gives 3.67 V — **over absolute maximum**. | 🟡 medium |
| 8 | TT motor stall current | 700 mA/motor, 1.5 A both | Feeds §1 and §4a. Doc says 500–700 mA; upper bound taken. | 🟢 low |
| 9 | LED V_f on J10 | 2.0 V (red) | Brightness only (§6). | 🟢 low |

---

## Summary of actions for v2

| Item | Section | Severity |
|------|---------|----------|
| Add on-board 4.7 kΩ I²C pull-ups — **blocker for the expander plan** | §5 | 🔴 |
| Add fuses (2 A) on `+BATT` and `+5V`; no overcurrent device exists | §2 | 🔴 |
| Resolve the `+BATT` = pack-or-5 V contradiction | §7 #1 | 🔴 |
| Add 10 µF bulk on `+3V3` | §0 | 🔴 |
| Place C3 next to U2 pad 9 — E1's fix moved VM 31.8 mm away | §0b | 🟡 |
| Change R6 20 kΩ → 15 kΩ for absolute-max margin on echo | §3b | 🟡 |
| Decide NeoPixel count / brightness cap against the 5 A budget | §4a | 🟡 |
| Keep C2 — it is what makes the 32 kΩ ADC source work | §3a | ℹ️ |
| Record that the battery divider is 2S-only | §3a | ℹ️ |
| Specify 1 oz copper explicitly on the order | §1 | 🟢 |
