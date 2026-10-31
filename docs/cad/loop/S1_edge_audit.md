# S1 accessible-edge audit (tick 18, 2026-10-31)

Tool: `uv run --project tools --extra cad python tools/edgeaudit.py --md docs/cad/loop/S1_edge_audit.md` (rerun after any edge pass). Convex edges with a dihedral turn > 30° in the generated STLs (`CAD/exports/gen`), filtered by where a child's hand reaches **with the canopy fitted**. Rule: accessible external edges r ≥ 1.0 mm (BACKLOG kid-safety).

| Part | Accessible zone | Sharp edges total (mm) | Accessible (mm) | Biggest accessible clusters (length @ x, y, z) |
|---|---|---|---|---|
| RB-PRT-001_base_plate | plate perimeter + belly | 5716 | 4506 | 426 @ (-4, -48, -8); 426 @ (-4, 46, -8); 261 @ (13, -35, -8); 261 @ (13, 35, -8); 78 @ (0, -26, -8); 78 @ (0, -1, -8) |
| RB-PRT-002_bulkhead | face side + outer sides | 3674 | 1647 | 126 @ (62, -47, 60); 126 @ (62, 47, 60); 344 @ (78, 23, 27); 74 @ (85, 0, 9); 58 @ (66, -47, 73); 58 @ (66, 47, 73) |
| RB-PRT-010_motor_mount_R | covered (motor, sprocket, canopy) | 805 | 0 | — |
| RB-PRT-011_motor_mount_L | covered (motor, sprocket, canopy) | 805 | 0 | — |
| RB-PRT-020_sprocket | outboard face | 3592 | 213 | 26 @ (11, -25, 0); 32 @ (8, 26, 0); 17 @ (-6, -27, 0); 29 @ (-27, -1, 0); 26 @ (27, -6, 0); 17 @ (-12, 25, 0) |
| RB-PRT-021_idler | outboard face | 3632 | 213 | 26 @ (11, -25, 0); 20 @ (8, 26, 0); 15 @ (-4, -27, 0); 17 @ (-6, 27, 0); 29 @ (-27, 1, 0); 26 @ (27, 6, 0) |

## After S1a (tick 21: plate outline top + bottom r 1.0)

| Part | Accessible zone | Sharp edges total (mm) | Accessible (mm) | Biggest accessible clusters (length @ x, y, z) |
|---|---|---|---|---|
| RB-PRT-001_base_plate | plate perimeter + belly | 4677 | 3466 | 296 @ (-4, -48, -8); 296 @ (-4, 46, -8); 261 @ (13, -35, -8); 261 @ (13, 35, -8); 78 @ (0, -26, -8); 78 @ (0, -1, -8) |
| RB-PRT-002_bulkhead | face side + outer sides | 3674 | 1647 | 126 @ (62, -47, 60); 126 @ (62, 47, 60); 344 @ (78, 23, 27); 74 @ (85, 0, 9); 58 @ (66, -47, 73); 58 @ (66, 47, 73) |
| RB-PRT-010_motor_mount_R | covered (motor, sprocket, canopy) | 805 | 0 | — |
| RB-PRT-011_motor_mount_L | covered (motor, sprocket, canopy) | 805 | 0 | — |
| RB-PRT-020_sprocket | outboard face | 3592 | 213 | 26 @ (11, -25, 0); 32 @ (8, 26, 0); 17 @ (-6, -27, 0); 29 @ (-27, -1, 0); 26 @ (27, -6, 0); 17 @ (-12, 25, 0) |
| RB-PRT-021_idler | outboard face | 3632 | 213 | 26 @ (11, -25, 0); 20 @ (8, 26, 0); 15 @ (-4, -27, 0); 17 @ (-6, 27, 0); 29 @ (-27, 1, 0); 26 @ (27, 6, 0) |

## After S1a2 (tick 26: load-rib bottoms + inboard boss rims r 1.0)

| Part | Accessible zone | Sharp edges total (mm) | Accessible (mm) | Biggest accessible clusters (length @ x, y, z) |
|---|---|---|---|---|
| RB-PRT-001_base_plate | plate perimeter + belly | 3423 | 2212 | 78 @ (0, -26, -8); 78 @ (0, -1, -8); 78 @ (0, 24, -8); 89 @ (-40, -26, -8); 78 @ (-40, -1, -8); 90 @ (-40, 26, -8) |
| RB-PRT-002_bulkhead | face side + outer sides | 3674 | 1647 | 126 @ (62, -47, 60); 126 @ (62, 47, 60); 344 @ (78, 23, 27); 74 @ (85, 0, 9); 58 @ (66, -47, 73); 58 @ (66, 47, 73) |
| RB-PRT-010_motor_mount_R | covered (motor, sprocket, canopy) | 796 | 0 | — |
| RB-PRT-011_motor_mount_L | covered (motor, sprocket, canopy) | 796 | 0 | — |
| RB-PRT-020_sprocket | outboard face | 3592 | 213 | 26 @ (11, -25, 0); 32 @ (8, 26, 0); 17 @ (-6, -27, 0); 29 @ (-27, -1, 0); 26 @ (27, -6, 0); 17 @ (-12, 25, 0) |
| RB-PRT-021_idler | outboard face | 3632 | 213 | 26 @ (11, -25, 0); 20 @ (8, 26, 0); 15 @ (-4, -27, 0); 17 @ (-6, 27, 0); 29 @ (-27, 1, 0); 26 @ (27, 6, 0) |

## After W3 (tick 27: 2.4 grid ribs, whole belly r 1.0)

| Part | Accessible zone | Sharp edges total (mm) | Accessible (mm) | Biggest accessible clusters (length @ x, y, z) |
|---|---|---|---|---|
| RB-PRT-001_base_plate | plate perimeter + belly | 1945 | 735 | 148 @ (-59, -33, -4); 148 @ (-59, 33, -4); 45 @ (45, 3, -4); 57 @ (79, -11, -4); 46 @ (84, 11, -4); 15 @ (32, -1, -4) |
| RB-PRT-002_bulkhead | face side + outer sides | 3674 | 1647 | 126 @ (62, -47, 60); 126 @ (62, 47, 60); 344 @ (78, 23, 27); 74 @ (85, 0, 9); 58 @ (66, -47, 73); 58 @ (66, 47, 73) |
| RB-PRT-010_motor_mount_R | covered (motor, sprocket, canopy) | 796 | 0 | — |
| RB-PRT-011_motor_mount_L | covered (motor, sprocket, canopy) | 796 | 0 | — |
| RB-PRT-020_sprocket | outboard face | 3592 | 213 | 26 @ (11, -25, 0); 32 @ (8, 26, 0); 17 @ (-6, -27, 0); 29 @ (-27, -1, 0); 26 @ (27, -6, 0); 17 @ (-12, 25, 0) |
| RB-PRT-021_idler | outboard face | 3632 | 213 | 26 @ (11, -25, 0); 20 @ (8, 26, 0); 15 @ (-4, -27, 0); 17 @ (-6, 27, 0); 29 @ (-27, 1, 0); 26 @ (27, 6, 0) |

## After S1b (tick 32: bulkhead outer side faces r 1.0)

| Part | Accessible zone | Sharp edges total (mm) | Accessible (mm) | Biggest accessible clusters (length @ x, y, z) |
|---|---|---|---|---|
| RB-PRT-001_base_plate | plate perimeter + belly | 1945 | 735 | 148 @ (-59, -33, -4); 148 @ (-59, 33, -4); 45 @ (45, 3, -4); 57 @ (79, -11, -4); 46 @ (84, 11, -4); 15 @ (32, -1, -4) |
| RB-PRT-002_bulkhead | face side + outer sides | 3145 | 1113 | 344 @ (78, 23, 27); 74 @ (85, 0, 9); 45 @ (65, 30, 75); 45 @ (65, -30, 75); 33 @ (52, 23, 122); 30 @ (59, -8, 97) |
| RB-PRT-010_motor_mount_R | covered (motor, sprocket, canopy) | 796 | 0 | — |
| RB-PRT-011_motor_mount_L | covered (motor, sprocket, canopy) | 796 | 0 | — |
| RB-PRT-020_sprocket | outboard face | 3592 | 213 | 26 @ (11, -25, 0); 32 @ (8, 26, 0); 17 @ (-6, -27, 0); 29 @ (-27, -1, 0); 26 @ (27, -6, 0); 17 @ (-12, 25, 0) |
| RB-PRT-021_idler | outboard face | 3632 | 213 | 26 @ (11, -25, 0); 20 @ (8, 26, 0); 15 @ (-4, -27, 0); 17 @ (-6, 27, 0); 29 @ (-27, 1, 0); 26 @ (27, 6, 0) |

## After S1c (tick 34: wheel outboard rims r 1.0)

| Part | Accessible zone | Sharp edges total (mm) | Accessible (mm) | Biggest accessible clusters (length @ x, y, z) |
|---|---|---|---|---|
| RB-PRT-001_base_plate | plate perimeter + belly | 1945 | 735 | 148 @ (-59, -33, -4); 148 @ (-59, 33, -4); 45 @ (45, 3, -4); 57 @ (79, -11, -4); 46 @ (84, 11, -4); 15 @ (32, -1, -4) |
| RB-PRT-002_bulkhead | face side + outer sides | 3145 | 1113 | 344 @ (78, 23, 27); 74 @ (85, 0, 9); 45 @ (65, 30, 75); 45 @ (65, -30, 75); 33 @ (52, 23, 122); 30 @ (59, -8, 97) |
| RB-PRT-010_motor_mount_R | covered (motor, sprocket, canopy) | 796 | 0 | — |
| RB-PRT-011_motor_mount_L | covered (motor, sprocket, canopy) | 796 | 0 | — |
| RB-PRT-020_sprocket | outboard face | 3419 | 41 | 31 @ (6, -3, 0); 10 @ (-6, 3, 0) |
| RB-PRT-021_idler | outboard face | 3459 | 41 | 31 @ (6, 1, 0); 10 @ (-4, -5, 0) |

## After S1a3 (tick 41: belly slot edges, partial)

| Part | Accessible zone | Sharp edges total (mm) | Accessible (mm) | Biggest accessible clusters (length @ x, y, z) |
|---|---|---|---|---|
| RB-PRT-001_base_plate | plate perimeter + belly | 1617 | 351 | 45 @ (45, 3, -4); 50 @ (84, -11, -4); 46 @ (84, 11, -4); 15 @ (32, 1, -4); 9 @ (-59, 26, -6); 9 @ (-80, -1, -6) |
| RB-PRT-002_bulkhead | face side + outer sides | 3145 | 1113 | 344 @ (78, 23, 27); 74 @ (85, 0, 9); 45 @ (65, 30, 75); 45 @ (65, -30, 75); 33 @ (52, 23, 122); 30 @ (59, -8, 97) |
| RB-PRT-010_motor_mount_R | covered (motor, sprocket, canopy) | 796 | 0 | — |
| RB-PRT-011_motor_mount_L | covered (motor, sprocket, canopy) | 796 | 0 | — |
| RB-PRT-020_sprocket | outboard face | 3419 | 41 | 31 @ (6, -3, 0); 10 @ (-6, 3, 0) |
| RB-PRT-021_idler | outboard face | 3459 | 41 | 31 @ (6, 1, 0); 10 @ (-4, -5, 0) |

## After S1a4 (tick 42: wire + tab slots)

| Part | Accessible zone | Sharp edges total (mm) | Accessible (mm) | Biggest accessible clusters (length @ x, y, z) |
|---|---|---|---|---|
| RB-PRT-001_base_plate | plate perimeter + belly | 1526 | 259 | 28 @ (84, -11, -4); 39 @ (84, 11, -4); 9 @ (-59, 26, -6); 9 @ (-80, -1, -6); 9 @ (30, -1, -6); 9 @ (-19, 44, -6) |
| RB-PRT-002_bulkhead | face side + outer sides | 3145 | 1113 | 344 @ (78, 23, 27); 74 @ (85, 0, 9); 45 @ (65, 30, 75); 45 @ (65, -30, 75); 33 @ (52, 23, 122); 30 @ (59, -8, 97) |
| RB-PRT-010_motor_mount_R | covered (motor, sprocket, canopy) | 796 | 0 | — |
| RB-PRT-011_motor_mount_L | covered (motor, sprocket, canopy) | 796 | 0 | — |
| RB-PRT-020_sprocket | outboard face | 3419 | 41 | 31 @ (6, -3, 0); 10 @ (-6, 3, 0) |
| RB-PRT-021_idler | outboard face | 3459 | 41 | 31 @ (6, 1, 0); 10 @ (-4, -5, 0) |

## Reading
- **No generated part has a single fillet yet** (the engine has `fillet` since T7, used nowhere in production). So "sharp" ≈ every edge, and the accessible column is the real to-do list.
- **Plate (4.5 m accessible):** the belly is the bulk: every rib bottom edge (load ribs at |y| 36.5 / 47: 426 + 261 mm per side) plus the 1.2 ribs and the boss rims, then the outline's top and bottom perimeter edges. The 1.2 mm ribs can't take r 1.0 per edge; give them a full round (r 0.6) or make them 2.4 and round. The belly faces the floor but is handled every time the robot is picked up.
- **Bulkhead (1.6 m):** side edges of the wall (x ~62–66, |y| 47, z 60–73), the face-board pocket rim and window (x ~78, z ~27), the foot front (x 85). The face side is what a child touches most.
- **Wheels (0.2 m each):** the outboard face's outer rim at r ~27 and the pocket edges on that face: r 1.0 on the rim (the running disc edge) keeps the belt's edge from being cut too.
- **Mounts:** hidden behind the motor and sprocket with the canopy on: not accessible, still listed (0.8 m) for the D1 internal-fillet pass.

## Fix items (added to BACKLOG)
- S1a plate: r 1.0 on the outline's top and bottom perimeter edges; round the rib bottoms (2.4 ribs r 1.0, 1.2 ribs full round); boss rims r 0.6.
- S1b bulkhead: r 1.0 on the outer side edges, the window rim and the foot front edge.
- S1c wheels: r 1.0 on the outboard rim (drivetrain.py layer stack gets a chamfer/round ring).
