# D3 print orientation per part (tick 30, 2026-10-31)

Tool: `tools/meshcheck.py` now splits the overhang (tick 30) into **bridges** (a flat underside with walls on both sides of one axis within 40 mm, which the slicer bridges), **ledges** (wall on one side only, cantilever > 1 mm) and **floating** area. Only ledges + floating need support. "Steep" = downward faces 45–80°, mostly fillets and tilted faces, normally printable.

Support area (ledge + floating, cm²) / steep (cm²) / height (mm) for each part axis pointing up:

```
RB-PRT-001_base_plate      +z:27.6/17/h32  -z:148.1/3/h32  +x:4.6/15/h170  -x:4.5/15/h170  +y:14.5/18/h110  -y:14.5/19/h110
RB-PRT-002_bulkhead        +z:2.6/19/h126  -z:1.4/21/h126  +x:6.2/79/h43  -x:1.0/79/h43  +y:9.7/7/h94  -y:10.3/7/h94
RB-PRT-003_pi_deck         +z:0.0/0/h3  -z:0.0/0/h3  +x:0.0/1/h111  -x:0.9/1/h111  +y:7.8/1/h59  -y:7.8/1/h59
RB-PRT-010_motor_mount_R   +z:0.0/0/h26  -z:4.7/1/h26  +x:6.8/1/h50  -x:5.9/1/h50  +y:3.8/2/h38  -y:9.5/1/h38
RB-PRT-011_motor_mount_L   +z:0.0/0/h26  -z:4.7/1/h26  +x:5.9/1/h50  -x:6.8/1/h50  +y:3.8/2/h38  -y:9.5/1/h38
RB-PRT-020_sprocket        +z:1.4/0/h36  -z:3.5/0/h36  +x:3.8/27/h55  -x:2.3/27/h55  +y:3.7/26/h55  -y:3.7/26/h55
RB-PRT-021_idler           +z:1.3/0/h36  -z:4.1/0/h36  +x:3.5/26/h55  -x:2.0/26/h55  +y:3.4/25/h55  -y:3.4/25/h55
RB-PRT-030_carriage_L      +z:2.1/2/h25  -z:2.4/2/h25  +x:0.6/2/h20  -x:0.4/2/h20  +y:4.0/0/h41  -y:3.1/0/h41
RB-PRT-031_carriage_R      +z:2.1/2/h25  -z:2.4/2/h25  +x:0.6/2/h20  -x:0.4/2/h20  +y:3.1/0/h41  -y:4.0/0/h41
```

## Decision (strength first, then support, then finish)

| Part | Up axis | Support cm² | Why |
|---|---|---|---|
| RB-PRT-001 plate | **+z** (ribs on the bed) | 27.6 | flat, so the plate's bending runs in-plane (XY strength). On edge (±x) needs only 4.5 but puts its bending across the layers: no. The 27.6 is the free strips outside the outer ribs (rear ~5 mm, sides 6.8, front 8–10) and the 40.6 mm front-centre bay between the ±21.5 ribs, just over the 40 mm bridge limit: **tree supports on the perimeter only**, or a later fix (45° underside skirt at the edge; ribs ≤ 40 mm apart) |
| RB-PRT-002 bulkhead | **−x** (face down) | 1.0 | lying flat, the wall's layers run parallel to the face, which takes S5's poke; the face side gets the textured PEI finish. 79 cm² "steep" is the 15° tilt and the foot, printable |
| RB-PRT-003 Pi deck | +z | 0 | flat plate |
| RB-PRT-010/011 mounts | +z (foot down) | 0 | the generated mirror is no longer flipped (tick 5 had 8.8 cm² on the old mirror part) |
| RB-PRT-020 sprocket, 021 idler | +z (outboard face down, drivetrain bed face) | 1.4 / 1.3 | as 08 designed them |
| RB-PRT-030/031 carriages | **−x** (front face down) | 0.4 | as P5 planned: one flat plane; the axle bore bridges |
