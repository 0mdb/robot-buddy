# Audio hardware: mic + speaker

**Status:** spec, 2026-10-30. Parts not yet ordered. Bench validation (§7) gates
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
        │  speaker grille below face ──►│  #3923 micro speaker faces forward (+X)
        │  [core board]  [Pi 5]         │  core board on base plate, short USB to Pi
        │══ base plate ═════════════════│
        └─ motors front (+X), idlers rear ┘
```

- **Mic disc on the canopy top, facing up.** The disc is circular, so it picks up a
  child on any side. It is the point farthest from both the motors (bottom front)
  and the speaker (front, below face). Keep **≥ 70 mm from the speaker cone centre**
  to the nearest mic.
- **Speaker fires forward**, at the child, below the TFT. It never fires up at the mics.
- **Core board** on the base plate near the Pi USB ports. The FPC runs ≤ 20 cm, with a
  loose loop and no sharp folds (bend radius ≥ 3 mm), and is secured so it cannot rattle.

### 4.2 Mic porting and vibration isolation

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

- ~~Sealed printed back box ~30 cc~~ (2026-11-05: the pre-boxed #3923 has its own back
  volume). The module is clamped into the bulkhead pocket through the TPU gasket
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

## 8. Software follow-ups (after hardware arrives)

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
