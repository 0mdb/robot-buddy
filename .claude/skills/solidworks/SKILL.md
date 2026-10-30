---
name: solidworks
description: Drive SOLIDWORKS 2024 from WSL over COM for robot-buddy's chassis — sync CAD/ to the Windows mirror, probe the running instance, list assembly references, script parts/assemblies in C# or VBScript. Use when Ben mentions SolidWorks, SLDPRT, SLDASM, the chassis, base plate, motor mounts, Pi holder, screen/face mount, speaker or mic mount, CAD/, sw.py, csc.exe, or asks to "open it in CAD", "build the assembly", "check the fit", "export STL". Also trigger when a macro "returns Nothing", a COM call gives "Type mismatch", or SolidWorks will not connect.
---

# SolidWorks automation (robot-buddy)

Ported from fpv250 on 2026-10-30, where these rules were paid for. Depth, dead
ends and worked snippets: `docs/cad/solidworks-api.md`. Design rules for the
printed parts: `docs/print-dfm.md`. Part index: `docs/cad/00_robot_buddy_index.md`.

## The loop

The **repo's `CAD/` is the master** (native SLDPRT/SLDASM in Git LFS).
SolidWorks cannot open `\\wsl.localhost\` paths, so it works on a mirror at
`C:\Users\Ben\robot-buddy-sw\CAD` and `tools/sw.py` syncs the two:

```
python3 tools/sw.py push            # repo -> mirror (before a CAD session)
python3 tools/sw.py probe           # SolidWorks reachable? what's open?
python3 tools/sw.py refs CAD/assemblies/RB-ASM-100_chassis.SLDASM
# ... edit in SolidWorks, Save, CLOSE the documents ...
python3 tools/sw.py pull -n         # see what changed
python3 tools/sw.py pull            # mirror -> repo, then git add / commit
```

(`just cad-push`, `just cad-pull`, `just cad-probe` wrap these.) Both directions use
`rsync --update`: a newer file on the receiving side is never overwritten.
`pull` warns about `~$` lock files: that document is open and may hold
unsaved work.

Generated scripts (.vbs/.cs) are staged under `C:\Users\Ben\robot-buddy-sw\tools\`
and must be **CRLF**. Run a `.vbs` like this; the filter drops WSL interop noise:

```
cmd.exe /c "cscript //nologo C:\Users\Ben\robot-buddy-sw\tools\x.vbs" \
  2>&1 | tr -d '\r' | grep -v "UNC\|CMD\|wsl" | grep -v '^$'
```

Compile C# with a `.bat` file, not `cmd.exe /c "<csc …>"`: quoted argv gets
mangled through WSL interop. `tools/sw.py:run_probe` is the worked pattern
(csc + DLLs copied next to the exe + trust the tool's last line).

## Chassis conventions

- Origin at the **base-plate top-face centre**; **+X forward** (drive end),
  **+Y left**, **+Z up** (`docs/cad/03_base_plate_design_spec.md`). Model every
  part in assembly coordinates where practical: then it needs no mates (rule 8).
- Bought parts go in as **envelopes** in `CAD/library/` (`*_envelope.SLDPRT`),
  with full vendor models in `CAD/library/vendor/` (native files only; raw
  STEP/STL downloads are gitignored, see `CAD/library/README.md`).
- Fits per `docs/print-dfm.md`: slip 0.3–0.4 mm/side, snug 0.15–0.25 mm.
  Heat-set inserts sized from the insert datasheet. Never print threads.

## Rules

1. **Write C#, not VBScript, for anything that imports a file, places a
   component, or passes an array.** VBScript cannot satisfy a COM
   `[in, out] long*` nor build a `SafeArray` of `DOUBLE`. That kills `LoadFile4`,
   `OpenDoc6`, `CreateTransform` and `CreateSpline` (*error 13, Type mismatch*).
   Use the in-box `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`
   (**C# 5**) against the two DLLs in `…\SOLIDWORKS\api\redist\`, **copied next
   to the exe**. Early binding turns a misremembered API name into a compile
   error. The names aren't guessable (it's `PrincipleMomentsOfInertia`).
2. **ONE agent at a time. SolidWorks is a single shared process.** Two COM
   clients loading into the same `SLDWORKS.exe` killed it five times
   (`0x800706BE`; the Windows Application log is the only place it shows).
   Serialise. Never overlap a review with a build, or a `pull` with a session.
3. **Start SolidWorks by hand.** An instance started by `CreateObject` never
   registers in the ROT, so nothing can attach to it. Never write a
   `CreateObject` fallback; fail loudly (`swprobe` does).
4. **Never call `swApp.LoadFile`.** It kills the process. The import call is
   `LoadFile4`.
5. **Cast every numeric argument explicitly** in VBScript (`CDbl`/`CLng`/`CBool`).
   *Symptom: the call returns `Nothing`, no error.*
6. **`ClearSelection2 True` before every `Insert3DSketch`.** It toggles; a
   just-closed sketch stays selected and gets re-entered.
7. **Always set `IComponent2::Transform2` explicitly, even for identity.**
   `AddComponent5`'s X,Y,Z places the **bounding-box centre**, not the origin.
8. **Parts modelled in assembly coordinates need no mates.** A mate only adds a
   constraint that can conflict later.
9. **STEP generated in Python: write it with OCCT's `STEPControl_Writer`**, not
   build123d's `export_step`. The latter wraps a Compound and SolidWorks opens
   it as an assembly (`E_NOINTERFACE` on the `IPartDoc` cast). Check
   `doc.GetType()` before casting, always.
10. **Do not trust the process exit code.** `cmd.exe` swallows .NET exit codes
    through WSL interop. Catch in `Main`, print a final status line (`PROBE OK`,
    `ALL CHECKS PASSED`), and have the caller check that line.
11. **Mass: set density with the document preference, then save and REOPEN.**
    `SetUserPreferenceDoubleValue(swMaterialPropertyDensity, kg_per_m3)`. Until
    reopened, mass reads ~0. Only the **assembly's** mass property is trustworthy
    for components. For printed parts take density from a **measured sliced
    mass**, never bulk × infill (out by 1.65× overall in fpv250).
12. **Verify by counting real features and measuring real geometry**, never
    because a call returned without error. Walk `FirstFeature`/`GetNextFeature`,
    count bodies with `IPartDoc.GetBodies2`, measure
    `Extension.CreateMassProperty().Volume * 1e9` for mm³.
13. **Nearest-neighbour vertex distance is the only shape test that has not
    lied.** Volume, bbox and centroid are identical for a part and its mirror.
    The L/R motor mounts are exactly that case.
14. **A symmetric checksum cannot detect a symmetry error.** Compare against a
    reference built a *different* way, and state the hypothesis your test can
    reject.
15. **Eyes before electrons.** On fpv250, nine geometry errors were caught by a
    human looking at a render and none by an automated check. Show Ben the part
    (screenshot / open it) before printing anything.

## Known state of the tree (2026-10-30)

- `RB-ASM-100_chassis.SLDASM` has 36 references. Three are **virtual**
  components (`Part2`, `MirrorPart2`, `Part8`) stored inside the assembly. Before
  printing them, save them out to `CAD/parts/` (right-click → Save Part (in
  External File)).
- The Pi 5 `SD CARD` sub-parts resolve to
  `C:\Users\Ben\Desktop\robots\buddy\model\PARTS\SD CARD\`, outside the repo.
  Fix it by opening the assembly from the mirror, using File → Find References / Replace
  to point at `CAD/library/vendor/RaspberryPi5/PARTS/SD CARD/`, then saving and
  pulling. Re-check with `sw.py refs`.
