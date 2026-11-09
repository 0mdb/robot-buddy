# Audio hardware: mic + speaker

**Status:** spec, 2026-10-30. Parts ordered 2026-11-05 (XVF3800 Flex, Same Sky speaker, PAM8302A). Bench validation (§7) gates
the CAD mounts. Replaces the two Amazon USB specials (`--usb-mic-device
plughw:2,0`, `--usb-speaker-device plughw:1,0` in `deploy/supervisor.env`).

## 1. Requirements

| # | Requirement | Why |
|---|---|---|
| R1 | Wake word ("hey buddy", openWakeWord) and Silero VAD work at 1–2 m in a family room | Core interaction |
| R2 | Mic hears through the robot's own speech: wake word and VAD stay live during TTS | Today the ear worker pauses VAD during playback and ignores wake words while listening (`supervisor/workers/ear_worker.py`). That is half-duplex because nothing cancels the echo. Barge-in needs AEC. |
| R3 | Motor and gear noise does not false-trigger the wake word or wreck STT | TT gearmotors sit about 100 mm from the mics |
| R4 | Intelligible child-friendly voice with a **hardware-bounded** loudness ceiling | Kid-safe; see §5 |
| R5 | Runs from the shared 5 V rail (`docs/power.md`). No 12 V rail exists. | Single-rail topology |
| R6 | 16 kHz mono PCM into the existing pipeline; minimal software change | `SAMPLE_RATE = 16000` in ear/TTS workers |
| R7 | Fits a 110 mm wide chassis (`docs/cad/03_base_plate_design_spec.md`) | Packaging |
| R8 | Buyable in Canada without a grey-market import | Ben is in Canada |

## 2. Decision: USB, with AEC on the audio device

**Use one USB audio device that has both the mics and the speaker output, and
runs AEC in hardware.** Don't use I2S.

AEC needs a reference signal sample-locked to what the speaker actually plays.
When the Pi plays through the same chip that captures the mics, the XMOS DSP
taps its own DAC feed as the reference. No clock drift, no loopback plumbing,
no Pi CPU cost. That is what unlocks R2.

| Option | AEC | Pi integration | Verdict |
|---|---|---|---|
| **XMOS XVF3800 USB array (mic + DAC + amp, one device)** | Hardware, reference internal | UAC2 class-compliant: `arecord`/`aplay`, no overlay | **Chosen** |
| I2S MEMS mics (INMP441 / SPH0645) + I2S amp (MAX98357A) | None. Software AEC (speexdsp / WebRTC AEC3) on the Pi needs an ALSA loopback reference and drift compensation; fragile, and costs CPU that STT/OWW need | dtoverlay; uses GPIO18–21; mic and amp share one I2S bus, so full duplex needs care | Rejected: cheapest, but does not meet R2 |
| ReSpeaker 2-Mic Pi HAT (WM8960) | None | HAT stacking conflicts with the UPS HAT (B) | Rejected |
| ReSpeaker Lite (XMOS XU316, 2 mics) | Claimed, thinly documented | USB, 35 × 86 mm, onboard speaker output | Budget fallback only: 2 mics, weaker far-field |
| Separate USB mic + USB speaker (status quo) | None, and two unrelated clocks | Two ALSA cards whose indices change between boots | Being replaced |

USB also keeps the GPIO header free and the device survives a Pi reflash
without overlays. The XVF3800 has an I2S firmware too, so this choice is reversible.

## 3. Bill of materials

### Mic / DSP: Seeed **reSpeaker Flex XVF3800, Circular-4** (USB firmware)

- XMOS XVF3800: AEC, 4-mic beamforming, noise suppression, de-reverb, AGC, DoA.
- **Split design**: a Ø73 mm circular mic board (4 PDM MEMS mics, 44 mm spacing,
  3 × M3) joined by a **20 cm 24-pin 0.5 mm FPC** to a separate core board (4 × M3).
  The mic disc goes where acoustics want it; the core board goes where the USB cable wants it.
- USB-C UAC2. Firmware options: 16 kHz/2-ch, 16 kHz/6-ch, 48 kHz/2-ch. **Use 16 kHz/2-ch**
  (matches R6; one channel is the processed ASR beam). Seeed documents Pi 5 use (arecord/aplay, dfu-util, Python tuning).
- Onboard TPA3139D2 class-D (JST), 3.5 mm jack (the jack overrides the JST speaker output).
- ≈ US$58 (RobotShop US). Canada: **ca.robotshop.com**, seeedstudio.com (ships to CA), DigiKey.ca (Seeed line).

Why the Flex over the standard **reSpeaker XVF3800 USB 4-Mic Array**: the standard
board is one Ø≈99 mm disc with mics, codec and LM48511 amp all on it. That leaves only
~5 mm per side in a 110 mm chassis, and the USB-C lands wherever the disc does. The
standard board is the **fallback** if the Flex is out of stock. Its LM48511 runs from
5 V (3 W into 8 Ω), so it needs no extra amp. It does have a mute button + LED,
which the Flex lacks.

### Amplifier: **Adafruit PAM8302A mono 2.5 W class-D** (Adafruit #2130), *conditional*

The Flex's TPA3139D2 is specified on a **12 V input** (Seeed tested 12 V/2 A). We
have no 12 V rail. Whether the onboard amp runs usefully from USB 5 V alone is
unverified (§7 step 2). If it does, skip this part. If not:

`Flex 3.5 mm jack → PAM8302A (5 V, gain trimmer) → speaker`

- 5 V supply from the shared rail. Add a 220 µF bulk cap at the amp.
- Into 8 Ω at 5 V it delivers ~1.5 W max, which suits §5.
- The AEC is unaffected: the reference is still the XVF DAC output; the analog amp
  just becomes part of the echo path the AEC models.
- ≈ US$4. Canada: DigiKey.ca, PiShop.ca, Elmwood Electronics, BuyaPi.ca.

### Speaker: **Same Sky CMS-30205-158L120-67** (30 × 20 × 5.6 mm, 8 Ω, 1.5 W, IP67 front) — ordered 2026-11-05

> Amendment (2026-11-05, Ben, Q25 a): the CE40P-8 (Ø40 × 23 deep + a 30 cc box) doesn't
> fit behind the bulkhead grille (tick 70: 7.9 mm to the motor mount). Replaced by a
> 30 × 20 micro speaker in the bulkhead pocket built for a 30 × 20 × 6 placeholder
> (`SPK_MOD` in `tools/chassis.py`, clamp RB-PRT-060, TPU gasket RB-PRT-061).

From the datasheet (rev 1.03, 2025-02-26; tolerance ±0.5 unless noted):

| | |
|---|---|
| Outline | **30 ± 0.3 × 20 ± 0.2**, rounded (oval) ends, not a rectangle; front face with a black net over the ports |
| Depth | **5.6 ± 0.3** overall; the back carries a Ø17 ± 0.2 magnet boss on a stepped frame (rear frame 28.5 × 18.5 outer, 25.2 × 15.2 inner) |
| Lead | 120 ± 5 mm, UL1571 30 AWG, exits the **short end in the plane of the frame**, with a glue blob 0.6 proud of the back; Molex 51021-0200 (PicoBlade 1.25, 2-pin) housing 4.2 × 3.2 × 4.0 |
| Electrical | 8 Ω (6.8–9.2); 1.5 W rated, 2.0 W max; Fo 900 Hz (720–1080); response Fo–20 kHz |
| SPL | 96 dB (93–99) at 1 W / **10 cm** → ≈ 88 dB at 25 cm, ≈ 76 dB at 1 m |
| Other | 4.6 g; IP67 (front side); −40…70 °C; T-S: Qts 4.6, Vas 0.0155 (free air) |

- A bare micro driver with a closed magnet back, not a boxed module: it needs a **seal round
  its front rim** so the front and back waves don't meet (acoustic short). The gasket must
  follow the oval, not the pocket's rectangle (see CAD notes).
- **Loudness (§5):** 1 W gives ≈ 88 dB at 25 cm, over the 85 dBA target, so the gain cap
  lands near 0.5 W. The PAM8302A (~1.5 W into 8 Ω at 5 V) stays inside the 1.5 W rating.
- Voice only (Fo 900 Hz): intelligible, thin, no bass. Fine for speech and for the AEC.
- CAD (next loop tick): `SPK_MOD` 30 × 20 × 6 → 30 × 20 × 5.6 with oval ends; gasket
  ring to the oval; pocket depth set so the clamp preloads the gasket (today the 7.2 mm
  stand-off leaves ~1.6 mm of air behind a 5.6 speaker: nothing presses it); a lead slot
  at one short end for the 120 mm lead + PicoBlade plug.
- Superseded: Adafruit #3923 (30 × 20 × 5, alternative), Dayton CE40P-8 (doesn't fit), Adafruit #3351 (bench only).

Confirm prices and stock before ordering. They were checked from search results, not live carts.

### Measured from the vendor files (2026-11-05)

Sources in `CAD/library/vendor/`: Seeed's DXF for the Flex (`ReSpeakerFlex/`; the STEPs, KiCad
exports dated 2026-02-10, are git-ignored like all vendor STEPs: re-fetch from
`https://files.seeedstudio.com/wiki/reSpeaker_flex/reSpeaker_xvf3800_flex_{circular_260210,Separate}.step`)
and the Same Sky datasheet PDF. Read with ezdxf / OpenCascade;
check against the boards when they arrive.

**Mic disc (circular-4)**
- Ø**72.5**, PCB **1.5** (STEP; the DXF has a 1.2 dimension, which may be the port Ø).
- **All parts on one face, ≤ 1.4 mm tall**; the other face is bare (logo, silkscreen).
- Mics: Infineon **IM69D130** (bottom-port), so the **ports open on the bare logo face**
  (Seeed: "the port is on the side with the logo"). **Bare face against the canopy**,
  components face into the robot: the canopy seat is flat, with 1.4 mm of relief under it.
- Mics on a **44 × 44 square**, at 45° to the hole pattern (radius ≈ 31.1).
- **3 × M3 holes, Ø3.3, Ø6 pads, on a Ø62.5 PCD at 0° / 120° / 240°.** A Ø52.5 circle on
  the drawing marks the inner layout.
- FPC: 24-pin 0.5 mm with a locking latch; its position isn't in the STEP (check on arrival).

**Core board**
- **70.5 × 52.2**, PCB 1.5, **4 × M3 Ø3.3 on 62.5 × 44.2** (4.0 in from each edge).
- Component side up to **9.0** above the board (2 × 4 header at 2.54 mm; two 470 µF cans at
  7.7); **1.6** below (through-hole leads). Envelope ≈ 70.5 × 52.2 × 12.1.
- One long edge (call it y 0) carries **USB-C** (x 29.5–38.4 from the corner, 1.3 proud
  of the edge, top 4.9), the **3.5 mm jack** (x 54.8–62.1, 2.0 proud, top 7.1) and a
  **JST PH 4-pin** (x 8.6–20.6). Plug room is needed off that edge: ~20 mm, or a right-angle cable.
- **Speaker output: JST PH 2.0 mm 2-pin, upright** (`PH-2A-M`), at x 11.4–17.4 near the
  opposite edge (y 46.9–51.6).

**PAM8302A (#2130):** 24 × 15 × 2 mm without the header, 1.4 g, 3.5 mm screw terminals
(about 10 mm tall). The page lists no mounting holes: plan a printed clip or foam tape.

**Speaker → wiring:** the CMS-30205 lead ends in a PicoBlade 1.25 plug; the Flex output is
JST PH 2.0 and the PAM8302A has screw terminals. Either cut the plug off for the terminals,
or crimp a PH 2-pin onto the lead.

### Order list (2026-11-05)

| Qty | Part | Where (Canada) | ≈ | Note |
|---|---|---|---|---|
| ✅ | Seeed **reSpeaker Flex XVF3800 Circular-4** (ordered 2026-11-05; check it shipped with USB firmware, else `dfu-util` per Seeed) | seeedstudio.com, ca.robotshop.com, DigiKey.ca | US$55–60 | The "with XIAO ESP32S3" kits ship I2S firmware. Some resellers show pre-order 4–8 weeks: check stock first |
| ✅ | Same Sky **CMS-30205-158L120-67** speaker (ordered 2026-11-05) | DigiKey | — | chosen over the #3923 |
| ✅ | Adafruit **#2130** PAM8302A 2.5 W mono amp (ordered 2026-11-05) | DigiKey.ca, PiShop.ca, Elmwood | US$4 | conditional (§7 step 2), but cheaper than a second order |
| 1 | Short **USB-A → USB-C** cable, 15–20 cm, right-angle C end if possible | any | — | Pi → core board |
| 1 | 1 mm **closed-cell foam, adhesive** (EPDM/neoprene) | any | — | mic-port gasket rings (§4.2) |
| — | Acoustic mesh / speaker cloth scrap | any | — | optional, behind the grille (§4.3) |

Printed, not bought: mic-disc grommets (TPU 95A, P8), speaker gasket RB-PRT-061, clamp RB-PRT-060.
On arrival: measure per §7 step 7 (disc, core board, mic port side, Flex speaker JST pitch, which short end the speaker lead should exit).

## 4. Placement, isolation and porting (drives the CAD)

### 4.1 Layout

```
        top canopy  ── mic disc (Ø73, ports UP, horizontal)        ← farthest from motors + speaker
        ┌───────────────────────────────┐
        │  TFT face (front, +X)         │
        │  speaker grille below face ──►│  CMS-30205 micro speaker faces forward (+X)
        │  [core board]  [Pi 5]         │  core board on base plate, short USB to Pi
        │══ base plate ═════════════════│
        └─ motors front (+X), idlers rear ┘
```

- **Mic disc on the canopy top, facing up.** The disc is circular, so it picks up a
  child on any side. It is the point farthest from both the motors (bottom front)
  and the speaker (front, below face). Keep **≥ 70 mm from the speaker cone centre**
  to the nearest mic.
- **Speaker fires forward**, at the child, below the TFT. It never fires up at the mics.
- > Amendment (2026-11-07, Ben: "put this mic in a position where it can work its best"; CAD
  > P6m): **the disc moves up into a round mic pod on the canopy top, roof level with the head
  > top.** Under the canopy top (port inlets z ≈ 97) the head stood ~27 mm higher only ~50 mm
  > ahead: the front ports could not see a talker in front below ~25° elevation (rear ports
  > ~15°), so a child sitting on the floor across the room, or lying at robot level, was behind
  > the head. The pod (RB-PRT-005, Ø77.6, PC) sits right behind the hood, centre (−5, 0); its
  > roof and the four port inlets are at **z 123.5**, level with the hood's front top edge
  > (123.54) and 1 mm over the bulkhead top: nothing on the robot is higher, so the view is
  > clear all round down to the horizon. It also helps DoA ("turn to whoever spoke").
  > Mics (−27 / 17, ±22); nearest mic to the speaker centre 115 mm (was 112; ≥ 70 holds).
  > Not round the camera: the disc is solid (the Ø52.5 circle in Seeed's DXF is a layout
  > line, not a hole), and the camera stays on the bulkhead, its view untouched (the pod is
  > behind and above the lens). The FPC drops through a 15 × 4 slot in the canopy skin under
  > the pod (x −12, y −23), then to the core board; its length still waits on K3.
- > Amendment (2026-11-08, Ben; CAD P6m2): **no pod: the disc hangs under a full-width hump
  > that is part of the canopy.** Ben: "a streamlined sturdy body and well protected mic, over
  > optimal placement. The top is still better than the front, most of the time people will
  > speak down to it." Roof z 110 (crowned 1.5; z 111.3 over the rear mics, 110.5 over the
  > front), disc centre (−5, 0), mics as before (−27 / 17, ±22). The head top (≈ z 122.5) now
  > stands ~12 mm over the front ports ~50 mm ahead, so a talker straight ahead below ~13°
  > elevation is shadowed; accepted. Speaker distance 112–115 (≥ 70 holds). Inside it is open
  > to the canopy: the FPC drops straight down, no slot. Supersedes RB-PRT-005 above.
- > Amendment (CAD tick 99, Q31 default): no flat spot fits the 70.5 × 52.2 board. It stands
  > on edge in the right (−y) side bay outboard of the Pi, parts facing the canopy wall, connector
  > edge down, on a wall that is part of the Pi deck (3 × M2.5). The USB-C points down into the
  > pocket between the right carriage and motor: **use a right-angle USB-C plug**; the cable runs
  > aft over the carriage to the Pi's USB-A. FPC from the disc ≈ 10–15 cm.
- ~~**Core board** on the base plate near the Pi USB ports.~~ The FPC runs ≤ 20 cm, with a
  loose loop and no sharp folds (bend radius ≥ 3 mm), and is secured so it cannot rattle.

### 4.2 Mic porting and vibration isolation

> Amendment (2026-11-05, Ben Q30 b, CAD tick 98): the Ø72.5 disc can't sit against the
> canopy ceiling (rib grid + keels), so it hangs under the ribs and each port is a Ø1.2 bore
> in a Ø3.2 tube from the top skin to the board: **port length ~5.7–6 mm, not ≤ 2 mm.**
> Rough Helmholtz check (port 1.13 mm², front cavity ~3 mm³): resonance ≈ 13–14 kHz, still
> above the 8 kHz band the 16 kHz pipeline uses. Verify in §7 (sweep or speech A/B against the
> bare board). Seal: a 1 mm closed-cell foam ring between each tube end and the board (tube
> reaches 0.3 into it). Float: M2.5 × 8 through the board's Ø3.3 holes (0.4 radial clear)
> with a 1 mm TPU washer each side, into M2.5 inserts in the canopy bosses.

> Amendment (2026-11-07, CAD P6m, mic pod): same scheme, moved into the pod. Each port is
> a Ø1.2 bore through the pod roof (1.8) and a Ø3.2 tube to 0.3 into the foam ring: **inlet
> to board 6.6 mm** (tick 98's canopy port was ~7.9 skin-to-board). Still not ≤ 2 mm: the
> roof needs ribs (the spokes) to take a heel, and the M2.5 insert needs 5.6 of roof + boss
> above the washer. Helmholtz estimate ≈ 12–13 kHz, above the 8 kHz band. The pod prints
> **roof down**, so the ports are vertical holes in the first layers and the tube ends (the
> foam's seal face) are clean top surfaces. **Float and fixing:** one M2.5 × 30 SHCS per
> disc hole, from inside the canopy: head in a counterbore in a canopy boss → canopy skin →
> canopy post Ø7 → TPU washer → disc → TPU washer → M2.5 × 4 insert in the pod's roof boss.
> The same three screws hold the disc and the pod; the disc floats between the washers as
> before; the pod rim floats 0.5 over the canopy skin.
>
> Amendment (2026-11-08, CAD P6m2, hump): the ports go through the hump roof (2.0 skin) into
> a Ø3.2 tube ending 0.3 into the foam ring: **inlet to board ≈ 8.0 (rear mics) / 7.3
> (front)**, still not ≤ 2 mm, for the same reasons (roof ribs, insert depth). Fixing: one
> **M2.5 × 8 SHCS** per disc hole, up from below: head → TPU washer → disc → TPU washer →
> M2.5 × 4 insert in a roof boss (07 F10). The canopy prints rear wall down, so the ports are
> horizontal holes in that print: drill them to Ø1.2 after printing if they close up.

- One acoustic port per mic: **Ø1.2 mm through-hole**, port length (canopy wall) **≤ 2 mm**
  so the port resonance stays well above the voice band. Align it to the MEMS port ±0.3 mm.
  **Confirm top-port vs bottom-port mics on the real board before modelling** (this
  decides which PCB face goes against the canopy).
- **Gasket each port**: a 1 mm closed-cell foam or silicone ring between the PCB and the
  canopy's inner face. Without it, sound leaks into the chassis cavity and the four mics
  hear the inside of the robot (motor whine, speaker back-wave), not the room.
- Optional: an acoustic mesh dot over each port (dust, sticky fingers).
- **Mechanically float the disc**: mount the 3 × M3 through TPU 95A or silicone grommets,
  not rigid PET-CF standoffs. That cuts structure-borne gear noise and speaker buzz,
  which the AEC handles poorly because it is non-linear.

### 4.3 Speaker enclosure and grille

- ~~Sealed printed back box ~30 cc~~ (2026-11-05: the CMS-30205 has a closed magnet back; it needs only a sealed front rim, no box
  ). The module is clamped into the bulkhead pocket through the TPU gasket
  (RB-PRT-061), not hard-bolted, so the chassis doesn't become a soundboard.
- **Grille**: openings **≤ 2 mm** (holes or slots), wall 1.5–2 mm, open area ≥ 35% of
  the cone area. Put a fine mesh or fabric behind it so a pencil or toothpick cannot
  reach the cone.
- No loose cables, screws or parts that can rattle near the speaker. Rattles are
  non-linear echo the AEC cannot cancel.

### 4.4 Motor noise (R3)

The defences, in order:

1. **Distance + geometry** (§4.1): the mics are at the top, the motors at the bottom front.
2. **Decoupling** (§4.2): grommeted mic disc; motor mounts are not shared with the canopy.
3. **XVF noise suppression + beamforming**: TT gear whine is mostly stationary, which is what NS removes well.
4. **Behaviour** (software, not hardware): optionally hold motion while `listening`.
   That decision belongs to the planner and is listed in §8.

Electrical: the PDM mics are digital on the board, so motor EMI on mic lines is not a
concern. Twist the speaker leads and route them away from the motor leads.

## 5. Loudness ceiling (kid-safe, R4)

- **Legal floor**: Canada's *Toys Regulations* (SOR/2011-17, "Auditory Hazards")
  forbid more than **100 dB** at the distance the toy is normally from the child's ear.
- **Our target** (much stricter): **≤ 85 dBA at 25 cm** at maximum volume, normal speech
  ≈ 65–70 dBA at 1 m.
- Layers, from hardware up:
  1. 8 Ω driver + 5 V amp → physically ≈ 1–1.5 W max into the 1.5 W CMS-30205 (≈ 88 dB at 25 cm per watt; SPL measured in §7 step 5).
  2. Amp gain (PAM8302A trimmer, or the XVF output gain saved to flash) set during §7 step 5, then **glued or recorded**.
  3. Supervisor hard cap: a `max_volume` config the dashboard slider cannot exceed
     (today it maps 0–100% straight through, `tts_worker.py` `TTS_CMD_SET_VOLUME`).
- The AEC also benefits: a quieter speaker that does not clip the mics keeps the echo path linear.

## 6. Power and connection

- One USB-A → USB-C cable from the Pi 5 to the core board. Audio in **and** out on one ALSA card.
- Expected draw: XVF board ≈ 0.2–0.3 A; PAM8302A ≈ 0.4 A peaks at max on 8 Ω, average far lower for speech.
- Pi 5 USB ports are limited to **600 mA total** unless the supply negotiates 5 A PD.
  The UPS HAT feeds the pogo pins, so set `usb_max_current_enable=1` in
  `/boot/firmware/config.txt` and confirm on the bench (§7 step 6). Better: feed the
  PAM8302A from the 5 V rail directly, not via USB.
- Address the card **by name**, never by index: `plughw:CARD=<name>,DEV=0` for both
  `--usb-mic-device` and `--usb-speaker-device`.

## 7. Bench validation (before any CAD is locked)

Bare boards on the bench with the Pi 5 running the supervisor:

1. **Enumerate**: `arecord -l`, `aplay -l`, `arecord --dump-hw-params`. Record the card name, channel map, and which channel is the processed ASR output.
2. **Onboard amp on 5 V**: does the Flex JST speaker output play at a usable level on USB power alone? Yes → drop the PAM8302A from the BOM.
3. **AEC / barge-in**: play TTS at max volume and record the ASR channel. Measure echo reduction. Count wake-word false triggers during playback, and the hit rate when someone says "hey buddy" over playback.
4. **Motor noise**: run the motors at 30/60/100% PWM. Count wake-word false accepts per hour and spot-check STT on a few phrases.
5. **SPL**: pink noise and TTS at max volume, measured with an SPL meter (a phone app is fine) at 25 cm and 1 m. Set the gain cap to meet §5.
6. **Power**: USB current at max volume; check `vcgencmd get_throttled` stays clean.
7. **Measure the boards**: mic disc, core board, FPC connector exit, mic port side, and hole positions. These feed the envelopes.

Pass → write the measured numbers back into this doc and build the envelopes.

> Amendment (2026-11-06, first bench, Flex on the Pi 5 over USB, bare boards, headphones on the
> 3.5 mm jack; speaker + PAM8302A not wired yet). Code fixes on branch `audio-xvf3800` (d53bb65).
>
> **Step 1, enumerate ✅**
>
> | Item | Measured |
> |---|---|
> | USB | `2886:001E` "reSpeaker Flex XVF3800 C16K6Ch", high speed. **Not** `001A` (that is the 4-Mic Array); the code and udev rule now take both |
> | Firmware | as shipped: **6 ch / 16 kHz** (`C16K6Ch`), `VERSION` 1.0.0. We had planned 2 ch; 6 ch works as is (`--usb-mic-channels 6`) |
> | ALSA card | id `C16K6Ch`; capture 6 ch S16_LE 16 kHz, playback 2 ch S16_LE 16 kHz; `match:reSpeaker` → `plughw:CARD=C16K6Ch,DEV=0` |
> | Mixer | `PCM` playback 0–60 (default 40 = −20 dB); `Headset` capture 60 (0 dB) |
> | Control | vendor interface 3 (WinUSB on Windows, libusb on the Pi). Every parameter in `PARAMS` reads except `GPO_READ_VALUES` (status 66); `AUDIO_MGR_OP_CH3..6` and `MUTE_FUNCTION_ENABLE` return 65; `LED_*` read nonsense (36) |
> | Array | `AEC_MIC_ARRAY_TYPE` 2 (square), mics at (±22.2, ±22.2) mm |
> | Defaults | `AUDIO_MGR_MIC_GAIN` 10, `REF_GAIN` 1.9, AGC on (max gain 32, desired level 0.0045), `PP_MIN_NS` 0.15, `PP_MIN_NN` 0.51, `AEC_ASROUTONOFF` 1, `AUDIO_MGR_OP_L` (8, 0), `AUDIO_MGR_OP_R` (7, 3) |
> | Mute | `GPI_VALUE` (pin 0, mute button) 0 = inactive; no red LED |
>
> **Channel map** (from a steady 1 kHz tone through a headphone held at the array, and speech):
>
> | Ch | Carries | Quiet room | Speech (250 ms windows) | 1 kHz tone |
> |---|---|---|---|---|
> | 0 | processed ASR output (`OP_L`), heavily noise-suppressed | −92 dBFS | −61 to −67 | removed (−130) |
> | 1 | second processed output (`OP_R` 7, 3; likely the auto-select beam), lighter suppression | −64 | −47 | removed (−105 to −118) |
> | 2–5 | the four raw mics, matched within 2.5 dB | −64 to −70 | −52 to −54 | −69 to −71 |
>
> **Ch 0 is clean but ~30 dB too quiet** for openWakeWord / STT as delivered. Raise it on the chip
> (`AEC_ASROUTGAIN`, `PP_AGCDESIREDLEVEL` / `PP_AGCMAXGAIN`) once mounted, since the enclosure
> changes the levels; compare ch 1 as the wake-word input at the same time.
>
> **Assembly catch: the mic FPC must go in with its exposed contacts toward the metal fingers in
> each connector.** Flipped, it seats and latches but the DSP gets no mic data and *every
> sample on every channel is exactly 0* (the DSP still runs, beam azimuths stay at their π/2
> default). Look into each open socket before inserting; the two ends can differ.
>
> **Other steps:** playback to the jack is clean (both channels). Step 3 (AEC) is **not tested**: a
> headphone is too weak to put speech above the room floor at the mics, so it waits for the
> speaker + amp. Steps 2, 4–7 and the DoA calibration wait for the speaker and for mounting.

## 8. Software follow-ups (after hardware arrives)

> Amendment (2026-11-06, Flex boards arrived; code on branch `audio-xvf3800`, cd92124): the plan, in order.
>
> **What the Flex gives us** (Seeed wiki + `xvf_host.py`, XMOS user guide v3.2.1). One USB-C
> cable carries two links. **Audio:** UAC 2.0, a normal ALSA card; Seeed's USB firmware comes
> as 2 ch / 16 kHz, 6 ch / 16 kHz or 2 ch / 48 kHz. Use **2 ch / 16 kHz**. **Its USB playback
> is the echo canceller's reference**, so every robot sound (TTS and chimes) must play
> through this card. **Control:** USB vendor requests on endpoint 0, VID:PID `2886:001A`:
> read = `0xC0, 0, 0x80|cmdid, resid`, reply = status byte (0 ok, 64 retry) + little-endian
> values; write = `0x40, 0, cmdid, resid`. Parameters used: `AUDIO_MGR_SELECTED_AZIMUTHS`
> (processed voice direction; NaN = no speech), `AEC_SPENERGY_VALUES` (speech energy per
> beam), `AEC_FIXEDBEAMS*` (lock a beam), `AUDIO_MGR_OP_L/R` (what each output channel
> carries), `AUDIO_MGR_MIC_GAIN` / `REF_GAIN`, `PP_AGC*`, `PP_MIN_NS` / `PP_MIN_NN`
> (noise suppression), `SAVE_CONFIGURATION`. Firmware via `dfu-util`.
>
> 1. **Bench** (§7 step 1 + `xvf_host.py -l`): card name, which output channel is the ASR
>    beam, the real parameter list for this firmware, and DoA sanity (talk from the front,
>    then the left → `--doa-offset-deg` / `--doa-sign`).
> 2. **Audio path** ✅ (code + tests): `--usb-mic-device match:<card>` / `--usb-speaker-device
>    match:<card>` resolve by card name (`supervisor/devices/alsa_device.py`);
>    `--usb-mic-channels 2 --usb-mic-channel N` captures stereo and keeps one channel as the
>    16 kHz mono stream for wake word, VAD and STT. udev rule for the control interface
>    (`deploy/99-robot-buddy.rules`), pyusb + libusb in install/update.
> 3. **Control client** ✅ (code + tests): `supervisor/devices/xvf3800.py` (read / write /
>    save, retry on busy, a fake board for tests). With `--xvf-control` the ear worker polls
>    voice direction at 10 Hz and publishes **`ear.event.doa`** `{speech, azimuth_deg (robot
>    frame, + = left, −180..180), energy, beam_energy[4]}` while someone talks, then one
>    `{speech: false}`.
> 4. **Use it** (next): eyes follow the voice (face gaze), turn toward the speaker after the
>    wake word (planner, reflex safety limits, not while driving), barge-in once §7 step 3
>    passes (keep wake word / VAD live during TTS, stop TTS on the child's voice), require
>    speech energy before accepting a wake word (motor-noise false wakes), lock a fixed beam
>    on the child during a conversation.
> 5. **Tune + dashboard**: gains and noise floors from the bench, `SAVE_CONFIGURATION` to
>    the board's flash; DoA dial + speech-energy meter in Studio.
> 6. **Privacy (Ben to decide before the canopy prints):** a parent-facing mute switch on the
>    FPC's `GPIO_1/2`, or software mute only.
>
> Amendment (2026-11-06, after the first bench, §7): the board ships with the **6 ch** firmware
> and enumerates as **`2886:001E`**; both are handled (d53bb65), the 2 ch firmware is no longer
> needed. **The voice pipeline gets refactored for this hardware** (Ben) rather than patched: one
> card for capture and playback, AEC on the board, chip setup at startup. See TODO "Voice
> pipeline refactor (XVF3800)".


- Ear worker: capture 2-ch from the XVF and pick the ASR channel (today `arecord` is mono).
- Device naming by ALSA card name in `deploy/supervisor.env`.
- Once §7 step 3 passes: keep VAD and wake word live during TTS (remove the pause-during-playback path), then barge-in.
- `max_volume` hard cap in the TTS worker (§5).
- Persist XVF tuning (AEC/AGC/NS, output gain) to device flash using Seeed's Python tool.
- Planner: optional "hold motion while listening" policy.
- Privacy: the Flex has no hardware mute button. Decide whether to add a physical mic-mute switch (parent-facing) or rely on the software mute.

## Sources

- Seeed wiki, reSpeaker Flex: https://wiki.seeedstudio.com/respeaker_flex_introduction/
- Seeed wiki, reSpeaker XVF3800 USB 4-Mic Array: https://wiki.seeedstudio.com/respeaker_xvf3800_introduction/
- XMOS XVF3800 user guide v3.2.1: https://www.xmos.com/documentation/XM-014888-PC/pdf/xvf3800_user_guide_v3.2.1.pdf
- TI LM48511: https://www.ti.com/product/lm48511
- Same Sky CMS-30205-158L120-67 datasheet: https://www.sameskydevices.com/product/resource/cms-30205-158l120-67.pdf
- Adafruit #3923 Mini Oval Speaker 8 Ω 1 W (alternative): https://www.adafruit.com/product/3923 (datasheet: https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/902/3923_Web.pdf)
- Dayton CE40P-8 (superseded): https://www.daytonaudio.com/product/1145/ce40p-8-1-1-2-mini-speaker-driver-8-ohm
- Adafruit #3351 / #4445 enclosed speakers: https://www.adafruit.com/product/4445
- Toys Regulations SOR/2011-17: https://laws-lois.justice.gc.ca/eng/regulations/sor-2011-17/page-1.html
