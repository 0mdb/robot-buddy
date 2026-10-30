> **Ported from fpv250** (`docs/solidworks-api.md` @ `c00c2f5`, 2026-10-09) on 2026-10-30.
> Sections 1–6 are general SolidWorks COM knowledge and apply here unchanged.
> Sections 7–8.x are fpv250 worked examples (fuselage, pods, CFD review) —
> keep them for the techniques, ignore the aircraft specifics. Staging here is
> `C:\Users\Ben\robot-buddy-sw\` (via `tools/sw.py`), not `fpv250-sw\`.
> Add buddy-specific findings to a new section at the end; do not re-sync from
> fpv250 wholesale.

# SolidWorks COM API — a working reference

Everything here was **run against SOLIDWORKS 2024 (rev 32.3.1)** on this
machine, driven from WSL2, and verified by measurement — feature counts, body
counts, volumes, centres of mass. Nothing in this document is from
documentation alone. Where an API returns success and does nothing, that is
recorded as a failure, because that is what it is.

Written while getting `fpv250`'s parametric frame into SolidWorks; the
findings are general and the next project (robot chassis) should start here
rather than rediscovering them.

---

## 1. The one thing that will waste your afternoon

**SolidWorks must be started by hand.** COM attach works through the Running
Object Table, and:

| how SolidWorks was started | in the ROT? | can a script attach? |
|---|---|---|
| by you, from the Start menu or `SLDWORKS.exe` | yes | yes |
| by a script calling `CreateObject("SldWorks.Application")` | **no** | **never** |

An instance a script starts is visible, usable, fully functional — and
permanently unreachable. `GetObject(, "SldWorks.Application")` returns
`Nothing` and `Marshal.GetActiveObject` throws `MK_E_UNAVAILABLE (0x800401E3)`.
The only cure is `taskkill /F` and relaunching it properly.

So **never fall back to `CreateObject`**. Fail loudly and tell the user to
launch SolidWorks instead. (`design/swmacro.py` used to have that fallback; it
has been removed for this reason.)

---

## 2. Pick your client: VBScript or C#

There is no usable MCP for SolidWorks, and none is needed — it is a COM
automation server. Three clients were tried.

### VBScript (`cscript //nologo x.vbs`) — good enough for geometry, blocked on two things

Works for the overwhelming majority of the API. It cannot do exactly two
things, and unfortunately they are load-bearing:

1. **It cannot build a `SafeArray` of `DOUBLE`.** VBScript's `Array()` makes a
   `SafeArray` of `VARIANT`. Some SolidWorks methods coerce it
   (`IMathUtility::CreatePoint`, `CreateVector` — both verified working);
   others reject it outright (`SketchManager::CreateSpline`,
   `IMathUtility::CreateTransform`).
2. **It cannot satisfy an `[in, out] long*` parameter.** Every file-import
   entry point has one, so *no VBScript can import a STEP file*. See §5.

It also cannot *read* a returned `SafeArray` of `DOUBLE`: `UBound()` works,
indexing throws `Type mismatch`. `TypeName()` reports `Double()`.

### PowerShell — broken, do not spend time on it

PowerShell can build `[double[]]`, so it looks like the answer. Its COM binding
to SolidWorks is broken: `$sw.GetType()` throws `TYPE_E_ELEMENTNOTFOUND` and
casting the RCW to `SolidWorks.Interop.sldworks.ISldWorks` fails. Confirmed
dead end.

### C# compiled with the in-box `csc.exe` — the real answer

This is the unlock, and it costs about two minutes to set up. .NET Framework
ships with a compiler already on the machine, and SolidWorks ships interop
assemblies:

```
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe
C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist\SolidWorks.Interop.sldworks.dll
C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist\SolidWorks.Interop.swconst.dll
```

A compiled client has real `ByRef`, real `double[]`, and early binding against
the type library, so **it hits none of the VBScript limits**. It is also
easier to debug: wrong member names are compile errors, not silent `Nothing`s.

Two traps:

- **That `csc.exe` is C# 5.** No string interpolation, no pattern matching, no
  `out` variables, no `nameof`. Write plain C# 5 or the errors are baffling.
- **The interop DLLs are not in the GAC.** Copy both next to your `.exe` or it
  throws `FileNotFoundException: Could not load file or assembly
  'SolidWorks.Interop.sldworks, Version=32.3.1.2…'` at run time despite having
  compiled fine.

Build line (put it in a `.bat` — quoting a path with spaces through
`cmd.exe` from a WSL shell does not survive):

```bat
@echo off
set CSC=C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe
set SWAPI=C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\api\redist
"%CSC%" /nologo /target:exe /platform:x64 /out:%~dp0%1.exe ^
  /reference:"%SWAPI%\SolidWorks.Interop.sldworks.dll" ^
  /reference:"%SWAPI%\SolidWorks.Interop.swconst.dll" %~dp0%1.cs
```

Attaching, with the retry that SolidWorks' `RPC_E_CALL_REJECTED` requires:

```csharp
static ISldWorks Connect()
{
    for (int i = 0; i < 60; i++)
    {
        try { return (ISldWorks)Marshal.GetActiveObject("SldWorks.Application"); }
        catch (COMException) { System.Threading.Thread.Sleep(1000); }
    }
    throw new Exception("no SolidWorks in the ROT -- start SLDWORKS.exe by hand");
}
```

**Rule of thumb:** use VBScript when you are only creating sketch geometry and
features; reach for C# the moment you need to import a file, position a
component, or pass an array.

### Look enum names up, do not remember them

`swconst` has thousands of constants and most forum answers are for older
versions. Twenty lines of reflection beats guessing:

```csharp
Assembly asm = Assembly.Load("SolidWorks.Interop.swconst");
foreach (Type t in asm.GetTypes())
    if (t.IsEnum)
        foreach (string n in Enum.GetNames(t))
            if (n.IndexOf(term, StringComparison.OrdinalIgnoreCase) >= 0)
                Console.WriteLine(t.Name + "." + n + " = " +
                                  Convert.ToInt64(Enum.Parse(t, n)));
```

That is how `swImportMultBodyAsPartData = 220` and
`swImportDissolveTopLevelAssemblyOnOpen = 701` were found in §4.8 — and how it
was established that no "import STEP as a part" toggle exists at all.

---

## 3. Driving Windows from WSL2

```bash
# scripts must be CRLF; write them that way, do not convert afterwards
python3 -c "open('/mnt/c/Users/Ben/fpv250-sw/x.vbs','wb').write(src.replace('\n','\r\n').encode())"

cmd.exe /c "cscript //nologo C:\Users\Ben\fpv250-sw\x.vbs" \
  2>&1 | tr -d '\r' | grep -v "UNC\|CMD\|wsl" | grep -v '^$'

wslpath -w /home/ben/foo      # -> \\wsl.localhost\... ; use a real C: path instead
```

Stage every file SolidWorks touches under a real Windows path
(`C:\Users\<you>\...`). Do not hand SolidWorks a `\\wsl.localhost\` UNC path.

`MsgBox` **blocks forever** under `cscript`. Detect the host:

```vb
isConsole = (LCase(fso.GetFileName(WScript.FullName)) = "cscript.exe")
Sub Report(t)
    If isConsole Then WScript.Echo t Else MsgBox t, vbInformation, "fpv250"
End Sub
```

Other VBScript syntax traps that cost real time:

- A comment after a `_` line continuation is a **compile** error.
- `1000000000#` (the VBA Double suffix) is not VBScript. Write `1000000000.0`.
- Roughly 25 line continuations maximum per statement. For long literal lists,
  build one big string and `Split()` it.
- Single-line `If ... Then a : b Else c` does not parse reliably. Use block
  `If`.

---

## 4. What works

### 4.1 Sketch geometry

```vb
Set ln = sm.CreateLine(x1, y1, z1, x2, y2, z2)   ' METRES, always
```

`CreateLine` takes six loose doubles — no array — which is why it is the only
usable primitive from VBScript. Measured throughput: 0.11-0.17 s per segment (1200 segments took 137 s on
one run and 207 s on another), so budget two to four minutes for a full
fuselage.

**`Insert3DSketch(True)` TOGGLES**, and closing a sketch leaves it *selected*,
so the next call **re-enters it** instead of starting a new one. Two sketches
silently merge into one. The fix is both halves of this:

```vb
swModel.ClearSelection2 True      ' otherwise the next open RE-ENTERS this sketch
sm.AddToDB = False
sm.Insert3DSketch True            ' open
sm.AddToDB = True                 ' True only while creating geometry
'   ... CreateLine ...
sm.AddToDB = False
sm.Insert3DSketch True            ' close
```

An empty sketch is discarded, so a failed geometry call leaves no trace at all.

### 4.2 Selection

```vb
ok = ext.SelectByID2(name, "SKETCH", 0, 0, 0, True, mark, Nothing, 0)
```

`True` = append to the selection list. `mark` is how the feature tells one role
from another — **mark 1 = loft profile**. Selection marks are the reason
`InsertProtrusionBlend` needs no profile arguments.

### 4.3 Loft — `FeatureManager.InsertProtrusionBlend`

17 positional arguments, in this order:

```
Closed, KeepTangency, ForceNonRational, TessToleranceOrPitch,
StartMatchingType, EndMatchingType, StartTangentLength, EndTangentLength,
StartTangentDir, EndTangentDir, IsThinBody, Thickness1, Thickness2,
ThinType, Merge, UseFeatScope, UseAutoSelect
```

**Every numeric argument must be explicitly cast.** This is the single
nastiest gotcha found:

```vb
' RETURNS Nothing, RAISES NO ERROR -- bare literals are VBScript Integers
Set blend = fm.InsertProtrusionBlend(False, True, False, 1, 0, 0, 1, 1, _
    True, True, False, 0, 0, 0, True, True, True)

' WORKS
Set blend = fm.InsertProtrusionBlend( _
    CBool(False), CBool(True), CBool(False), CDbl(1.0), _
    CLng(0), CLng(0), CDbl(1.0), CDbl(1.0), _
    CBool(True), CBool(True), CBool(False), CDbl(0.0), CDbl(0.0), _
    CLng(0), CBool(True), CBool(True), CBool(True))
```

Suspect this pattern any time a call "returns Nothing with no error": the
argument types did not match and the call never reached SolidWorks.

Leave `StartMatchingType`/`EndMatchingType` at 0 (None). Measured on this
body: a tangency/spline blend overshoots *between* profiles and gets worse,
not better, as profiles are added. Profile count is the lever, not blend type.

### 4.4 Documents and templates

```vb
tmpl = swApp.GetUserPreferenceStringValue(8)    ' part      .prtdot
tmpl = swApp.GetUserPreferenceStringValue(9)    ' assembly  .asmdot
tmpl = swApp.GetUserPreferenceStringValue(10)   ' drawing   .drwdot
Set doc = swApp.NewDocument(tmpl, 0, 0, 0)
swApp.QuitDoc doc.GetTitle                      ' close WITHOUT saving
swApp.CloseDoc doc.GetTitle                     ' close, prompting as usual
swApp.CloseAllDocuments True                    ' True = discard changes
```

All three constants **verified by printing the returned path** — do that
rather than trusting an enum table.

### 4.5 Opening a *native* document from VBScript

`OpenDoc6` is unusable from VBScript (§5), but `OpenDoc7` takes a
`DocumentSpecification` object and has **no `[in, out]` arguments at all**, so
it works fine — for native `.SLDPRT`/`.SLDASM`/`.SLDDRW` only. It will not run
a translator, so it cannot open a STEP.

```vb
Set spec = swApp.GetOpenDocSpec("C:\path\thing.SLDASM")
spec.ReadOnly = False
Set doc = swApp.OpenDoc7(spec)
If doc Is Nothing Then WScript.Echo "err=" & spec.Error & " warn=" & spec.Warning
```

`spec.Error` uses `swFileLoadError_e`; `1024` is what you get for handing it a
file it has no business opening.

### 4.6 Measurement — the only honest verification

```vb
Set mp = swModel.Extension.CreateMassProperty
vol = mp.Volume * 1000000000.0       ' m^3 -> mm^3.  ".0", not the VBA "#"
```

`IMassProperty.CenterOfMass` returns metres, in the document's own coordinates.

Body count — note **`GetBodies2` is on `IPartDoc`, not `IModelDoc2`**. Late
binding hides that; C# will not compile it:

```csharp
Array ba = ((IPartDoc)doc).GetBodies2((int)swBodyType_e.swSolidBody, true) as Array;
int solids = ba == null ? 0 : ba.Length;
```

Feature-tree walk, for counting what actually got built:

```vb
Set f = swModel.FirstFeature
Do While Not f Is Nothing
    If f.GetTypeName2 = "3DProfileFeature" Then k = k + 1   ' a 3D sketch
    Set f = f.GetNextFeature
Loop
```

Useful `GetTypeName2` values seen: `3DProfileFeature` (3D sketch),
`ProfileFeature` (2D sketch), `Blend` (loft), `RefPlane`, `SolidBodyFolder`.

### 4.7 Importing a STEP — **C# only**

```csharp
int errs = 0;
IModelDoc2 doc = (IModelDoc2)sw.LoadFile4(path, "", null, ref errs);
```

Verified: imports as **one solid body** with volume matching the OCCT source
to 0.00% on prismatic/revolved parts. On large spline-surface parts SolidWorks'
own healing differs slightly from OCCT's — measured **+0.046%** and
**−0.083%** on the two cowls. Budget ~0.1%, not 0.

That delta is genuinely SolidWorks re-knitting the B-rep, and **not** a
difference in the exported file: the two cowl STEPs were re-exported after a
model change and came back byte-for-byte equivalent (same volume to 0.01 mm³,
same centroid, same 10 and 11 faces), yet SolidWorks reproduced the same
offsets. A 10-face spline body is where it shows up; a 102-face prismatic body
(`core_body`) imports at +0.000%.

Then save it so it can be used as an assembly component:

```csharp
int e = 0, w = 0;
doc.Extension.SaveAs(dst, (int)swSaveAsVersion_e.swSaveAsCurrentVersion,
                     (int)swSaveAsOptions_e.swSaveAsOptions_Silent,
                     null, ref e, ref w);
```

### 4.8 When a STEP arrives as an **assembly**, not a part

`GetBodies2` is on `IPartDoc`, so this blind cast kills the process outright:

```
System.InvalidCastException: Unable to cast COM object of type
'ModelDoc2Class' to interface type 'IPartDoc' ... E_NOINTERFACE
```

Always check `doc.GetType()` against `swDocPART` before casting.

**SolidWorks decides part-vs-assembly from the STEP's own structure, and you
cannot override it.** A file containing `NEXT_ASSEMBLY_USAGE_OCCURRENCE` opens
as `swDocASSEMBLY` (type 2) no matter what. Tried and measured, all three made
no difference:

| toggle | id | result |
|---|---|---|
| `swImportMultBodyAsPartData` | 220 | still type 2 |
| `swMultiCAD_Enable3DInterconnect` | 691 | still type 2 |
| `swImportDissolveTopLevelAssemblyOnOpen` | 701 | still type 2 |

Nor can you dig the part out of the result: with 3D Interconnect on, the
single component's `GetModelDoc2()` is itself **another assembly**, living in
`%TEMP%\swx*\IC~~\`.

The fix is upstream, in the file. `arm_tube.step` was two products —
`PRODUCT('COMPOUND')` wrapping a child — because the model exports that solid
inside a `Compound`. build123d's `export_step` always wraps, so re-exporting
even a bare `Solid` through it still emits two products. Drop to OCCT's writer:

```python
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.STEPControl import STEPControl_StepModelType, STEPControl_Writer

w = STEPControl_Writer()
w.Transfer(solid.wrapped, STEPControl_StepModelType.STEPControl_AsIs)
assert w.Write(dst) == IFSelect_ReturnStatus.IFSelect_RetDone
```

One product, no occurrences, identical volume and centroid to four decimals —
and SolidWorks then reports `doctype=1, solids=1`. `swassembly.py` does this
automatically for any staged STEP whose text contains
`NEXT_ASSEMBLY_USAGE_OCCURRENCE`, and leaves the rest alone.

**If you touch a user preference, restore it.** `GetUserPreferenceToggle`
first, set, and put it back in a `finally` — these are the user's global
settings, not your process's.

### 4.9 Density, mass and inertia

Mass properties are meaningless until the parts have a density. Setting one by
script is easy, as long as you avoid the material library.

`IPartDoc::SetMaterialPropertyName2` needs the material to already exist in a
SolidWorks material database, which means shipping and registering a library —
a lot of machinery for a number. The document-level density preference needs
only the number, and it **persists into the saved file**:

```csharp
doc.SetUserPreferenceDoubleValue(
    (int)swUserPreferenceDoubleValue_e.swMaterialPropertyDensity, 2700.0);  // kg/m^3
doc.EditRebuild3();
```

`swMaterialPropertyDensity` is **7**. Units are SI throughout: density kg/m³,
`IMassProperty.Mass` kg, `CenterOfMass` metres, moments kg·m².

> **TRAP: the mass you read from a part document is wrong.** An `IMassProperty`
> created immediately after the density change reported **0.0002 g** where
> 0.6044 g was correct — neither the old value nor the new one. Save, close and
> reopen and it reports 0.6044 g exactly; the density survives the round trip.
> Worse, a part opened as an **assembly component** keeps reporting 0.0002 g no
> matter what, so `comp.GetModelDoc2().Extension.CreateMassProperty().Mass` is
> not usable. The **assembly's own** mass property is correct. Derive each
> component's mass as `volume_mm3 × density_kgm3 × 1e-6` grams and check the
> assembly total against that sum.

> **TRAP: close the ASSEMBLY before the parts, or the save silently fails.**
> An open assembly holds its components open, and a document SolidWorks holds
> cannot be saved over — `Extension.SaveAs` returns **error 1**, which reads
> like nothing in particular. Closing the parts first does not help; the
> assembly still has them. A run here set every density correctly, had all 16
> saves refused, and then built an assembly from the *previous* part files at
> the default 1000 kg/m³ — reporting 289.8 g where 227.8 g was expected. Walk
> the open documents and close everything under the staging directory,
> **assemblies first, then parts**, rather than guessing at titles.

Inertia comes off the same object, but note the spelling:

```csharp
double[] pmoi = (double[])amp.PrincipleMomentsOfInertia;   // NOT "Principal"
double[] axes = (double[])amp.PrincipleAxesOfInertia;
```

SolidWorks uses **"Principle"**. `PrincipalMomentsOfInertia` is a compile
error, which is one more argument for the compiled client — in VBScript it
would have been a silent `Nothing`. Both were found by reflecting over the
interop assembly rather than guessing:

```csharp
foreach (MemberInfo m in Assembly.Load("SolidWorks.Interop.sldworks")
                                 .GetTypes().First(t => t.Name == "IMassProperty")
                                 .GetMembers())
    Console.WriteLine(m.MemberType + " " + m.Name);
```

**Where the density comes from matters more than how you set it.** For printed
parts, do not compute `bulk × infill`. That formula is structurally wrong for
small shelled parts — perimeters, top and bottom solid layers and the solid
material around every bore are all 100% dense, and the nominal infill applies
only to what is left. Measured against OrcaSlicer on this frame it under-read
by **1.65× overall**, and not uniformly: 0.90× on the cowls (genuine shells, so
the formula happens to work) to **3.64×** on the arm fairing, which at 13 mm
thick is essentially all perimeter. No single correction factor exists. Slice
the parts, read the gram figure, and divide by the measured volume.

A measured mass then has its own failure mode: **staleness**. A sliced mass for
geometry that has since moved is worse than an estimate, because it looks
authoritative. `design/sliced_mass.json` carries a sha256 of `design_vars`, and
`swassembly.py` refuses to run against a record whose fingerprint does not
match rather than falling back to a formula and calling the result measured.

Two things the fingerprint does **not** do, both worth knowing:

- **It proves only what it hashes.** `design_vars` excludes `aero.polar`, so a
  re-run of the polar changes trim pitch, which rotates the pods, which moves
  the assembly CG — with the fingerprint still matching. Rotation preserves
  volume, so the sliced *masses* stay valid; the *positions* do not. Record
  which polar a CG was computed against.
- **It proves the parameters match, not that anyone re-measured.** A record can
  carry a fresh fingerprint and stale grams. `swassembly.py` therefore also
  checks each recorded `volume_mm3` against the regenerated geometry: a record
  taken on different shapes will have different volumes even when the
  fingerprint agrees. That check is what showed a record described as stale was
  in fact live — all five volumes matched to 0.000%, which a stale record
  cannot do.

**Point masses.** `IMassProperty` also exposes `SetAssignedMassProp`,
`SetOverrideMassValue` and `SetOverrideCenterOfMassValue`, which would let a
component carry a mass with no geometry. Not used here: an override is
invisible in the tree and hard to check afterwards. `swassembly.py --masses`
instead inserts 6 mm cubes with the density tuned to hit the target mass, named
`mass_motor_FL`, `mass_battery` and so on. Fake density, real arithmetic, and
every one of them verifiable by measurement — which matters more than elegance
when the whole point is a number someone will trust.

### 4.10 Assemblies — and the trap in `AddComponent5`

```csharp
IModelDoc2 asmDoc = (IModelDoc2)sw.NewDocument(asmTemplate, 0, 0, 0);
IAssemblyDoc asm = (IAssemblyDoc)asmDoc;

// AddComponent5 will not load a part that is not already open.
int oe = 0, ow = 0;
sw.OpenDoc6(partPath, (int)swDocumentTypes_e.swDocPART,
            (int)swOpenDocOptions_e.swOpenDocOptions_Silent, "", ref oe, ref ow);
sw.ActivateDoc3(asmDoc.GetTitle(), false,
                (int)swRebuildOnActivation_e.swDontRebuildActiveDoc, ref oe);

IComponent2 comp = (IComponent2)asm.AddComponent5(partPath,
    (int)swAddComponentConfigOptions_e.swAddComponentConfigOptions_CurrentSelectedConfig,
    "", false, "", 0.0, 0.0, 0.0);
```

> **`AddComponent5`'s X, Y, Z do NOT place the part's ORIGIN at that point.
> They place the part's BOUNDING BOX CENTRE there.**

This is easy to miss, because for a part modelled about its own origin the two
are the same. For a part modelled *in assembly coordinates* — which is exactly
what you want if you are exporting from a parametric model — the component
arrives displaced by minus its own box centre. Measured, adding a part whose
geometry sits at (45.96, 45.96, −5.41):

```
AddComponent5(..., 0,0,0)  ->  Transform2 translation = (-45.962, -45.962, +5.415)
```

SolidWorks silently inserted the compensating shift. **Always overwrite
`Transform2` explicitly, even for an identity placement:**

```csharp
comp.Transform2 = (MathTransform)RotZ(0);   // not "skip it when rot == 0"
```

### 4.11 Transforms

`IMathTransform.ArrayData` is 16 doubles:

| index | meaning |
|---|---|
| 0–8 | 3×3 rotation, **row-major** |
| 9–11 | translation, **metres** |
| 12 | uniform scale |
| 13–15 | unused, 0 |

In C#, build one directly:

```csharp
double[] d = new double[16];
d[0]= c; d[1]=-s; d[2]=0;
d[3]= s; d[4]= c; d[5]=0;
d[6]= 0; d[7]= 0; d[8]=1;
d[12]=1;
IMathTransform t = (IMathTransform)mu.CreateTransform(d);
```

In VBScript, `CreateTransform` is unreachable (§5) but this **is** available
and covers any rotation about a line:

```vb
Set mu = swApp.GetMathUtility
Set p  = mu.CreatePoint(Array(0.0, 0.0, 0.0))     ' VARIANT array accepted
Set v  = mu.CreateVector(Array(0.0, 0.0, 1.0))    ' VARIANT array accepted
Set t  = mu.CreateTransformRotateAxis(p, v, CDbl(angleRadians))
```

To apply a transform by hand (component space → assembly space):

```
x_asm = R * x_part + translation      R from ArrayData[0..8], row-major
```

### 4.12 Splines — C# only, but they do work

The polyline-per-section approach in `swmacro.py` is a **VBScript** workaround,
not a SolidWorks limitation. From a compiled client, with a real `double[]` of
flat XYZ triples in metres:

```csharp
double[] pts = new double[n * 3];          // x0,y0,z0, x1,y1,z1, ...  METRES
object sp  = sm.CreateSpline((object)pts);
object sp2 = sm.CreateSpline2((object)pts, true);   // true = closed
```

Verified: both return a real segment, and walking the sketch afterwards shows
`ISketchSegment.GetType() == 3` (spline). So a future version of the export
could hand SolidWorks 25 spline profiles instead of 25 × 48 line segments —
one feature per section instead of 1200 `CreateLine` calls, and about three
and a half minutes of wall clock saved.

Not done here on purpose: the Python model builds each section as a polyline
too, so the polyline route reproduces the model's own construction rather than
approximating it, and the measured agreement (§7) is already 0.3%.

---

## 5. What does not work, and why

| API | Symptom | Cause / verdict |
|---|---|---|
| `SketchManager.CreateSpline` / `CreateSpline2` | returns `Nothing`, no error | **VBScript only.** It wants `SafeArray` of `DOUBLE`; VBScript makes `VARIANT`. From C# with a real `double[]` **both work** — see §4.12. |
| `SketchManager.CreateSpline3` | `Type mismatch` (err 13) | same, plus object args |
| `InsertCurveFileBegin` / `InsertCurveFile` / `InsertCurveFileEnd` | `InsertCurveFile` returns `True`, `InsertCurveFileEnd` returns **`False`**, no feature appears | fails identically on a 4-point control file, so it is not the data. Dead end. |
| `swApp.LoadFile4(…, ref errs)` from VBScript | `Type mismatch` (err 13) | `[in, out] long*`. Fails with a literal `0`, an uninitialised `Dim`, and a `CLng` alike — not a ByRef-binding detail you can dodge. |
| `swApp.OpenDoc6(…, ref e, ref w)` from VBScript | `Type mismatch` (err 13) | same |
| `swApp.OpenDoc7(spec)` on a `.step` | returns `Nothing`, `spec.Error = 1024` | `OpenDoc7` opens SolidWorks documents; it does **not** run a translator. `GetOpenDocSpec` reports `DocumentType = -1` for a STEP. |
| `IMathUtility.CreateTransform(Array(...))` from VBScript | `0x80020009` (DISP exception) | needs `double[16]`. C# only. |
| indexing a returned `Double()` in VBScript | `UBound` works, `arr(i)` → `Type mismatch` | VBScript can only index `SafeArray` of `VARIANT` |
| `IComponent2.GetBox(false, false)` | plausible-looking but wrong numbers | for a component whose `Transform2` was never assigned it returns a box centred on (0,0,0) with a part-space size. Do not verify positions with it — use `Transform2` × the part's centre of mass. |
| `swApp.GetErrorMessages` | `Argument not optional` | not the no-arg accessor you want |
| **`swApp.LoadFile(path)`** | **CRASHES SOLIDWORKS** | returns `0x800706BE` (RPC failed) and the process dies, taking unsaved work with it. Never call it. |
| PowerShell COM | `TYPE_E_ELEMENTNOTFOUND` on `$sw.GetType()` | binding broken; early-binding cast also fails |
| FeatureWorks on an imported STEP | no tree recovered | it recognises prismatic features; a superellipse loft is not one |
| `IModelDoc2.RayIntersections` | `RPC_E_SERVERFAULT` (0x80010105) on every option / radius / offset combination tried | it is on **`IModelDoc2`** (6 args) — the `ModelDocExtension` overload takes a 7th `HighPrecision` — but the results come back from **`IModelDoc2::GetRayIntersectionsPoints`**, which has no extension overload at all. Even called correctly it faulted here. Use a temp-body boolean probe instead (§8.2). |
| `IBody2.GetTessTriangles` | compile error, no such member | tessellation is on **`IFace2`**, not `IBody2`. `IBody2` only offers `GetTessellation` / `IGetTessellation`. Walk the faces and concatenate. |
| reading `IModelView.Orientation3` right after `ShowNamedView2` | a plausible, wrong, *changing* matrix | the view transition is **animated**, and it only advances when SolidWorks gets idle time. Six successive attaches sampled six different orientations. Poll until two reads agree before believing one (§8.5). |

Two failure *shapes* worth internalising:

- **Returns `Nothing`, raises nothing** → argument type mismatch. Cast
  everything explicitly.
- **Returns `True`/a feature, and nothing appears** → it really did nothing.
  Count features, count bodies, measure volume.

---

## 6. Verification discipline

This is not optional here; several of these APIs return success and do nothing.

1. **Never count loop iterations.** An early version of `swmacro.py` reported
   "16 sketches built" while SolidWorks held **8 sketches with doubled
   contents** — `Insert3DSketch` toggling, as in §4.1. Walk the tree with
   `FirstFeature`/`GetNextFeature` and count `GetTypeName2`.
2. **Check the count after every step, and abort on mismatch**, rather than
   discovering it at the end.
3. **Measure volume**, and compare against something computed outside
   SolidWorks.
4. **Verify positions with transforms and centres of mass**, not bounding
   boxes.
5. **Print the constant, do not trust the enum.** `GetUserPreferenceStringValue(9)`
   returning a path ending `.asmdot` is proof; "9 is
   swDefaultTemplateAssembly" is a memory.
6. **A self-consistent assembly can still be wrong.** The worst bug found here
   was not an API failure at all. Four of sixteen components were placed by
   rotating an exported part onto another station, when the model does not
   build them that way (§7). Every check passed — same volume, same bounding
   box, assembly volume matching the sum of its parts to +0.000%, component
   transforms agreeing with the assembled solid to 0.001 mm, and one nacelle's
   own centre of mass **0.0001 mm** from correct while its vertices were
   **11.8 mm** out.

   *A congruent solid in the wrong place is invisible to every scalar you are
   likely to measure.* Three things follow:

   - **Compare against a reference that contains the real answer**, not one you
     derived the same way you built the thing. The rotation-built assembly's X
     centroid was exactly 0.000 because a rotationally-reconstructed airframe
     is symmetric by construction; the model's is −0.149 mm. A checksum that
     can only come out perfect is not a check.
   - **Compare shapes by nearest-vertex distance** when it matters — 0.000000
     mm for a real match, 10.9–130 mm for every near-miss. It must be
     *nearest-neighbour*: sorting both vertex lists and comparing elementwise
     pairs the wrong points when coordinates are near-tied, and reports tens of
     millimetres between shapes that coincide exactly.
   - **Know what hypothesis your test can reject.** The diagnostic written to
     catch this bug compared each instance against *rotations about the
     origin*, found nothing, and reported the nacelles "unrelated" — when in
     fact they are one part differing by pure **translation**, which that
     family cannot express (§7). A negative result bounds the candidate set,
     not the design. Reading it as a fact about the design turned a tooling
     limitation into a confident, wrong claim about how the aircraft is built.

   The structural fix was to stop inferring placement altogether — see §7.
7. **Watch for checks that only work because of a degeneracy.** The assembly
   CG check compared `IMassProperty.CenterOfMass` against a **volume-weighted**
   prediction. That was correct for as long as every part had the same density,
   because then the centroid and the centre of mass are the same point. Give
   the parts real densities and they separate — 0.27 mm apart on Z here — and
   the check started failing on a build that was entirely correct. A check that
   passes for a reason you did not intend will fail the moment that reason
   stops holding, and it will look like a regression in the thing being
   checked.
8. **Do not trust the process exit code.** An unhandled .NET exception in
   `swtool.exe` came back through `cmd.exe` and the WSL interop layer as
   **returncode 0**, and the Python wrapper reported success on a run that
   crashed before it ever built the assembly. Catch exceptions in `Main` and
   return a number yourself, *and* have the caller check the tool's own final
   line (`ALL CHECKS PASSED`) rather than the exit status.

---

## 7. The fpv250 flow, end to end

```bash
cd design

# A. the fuselage as a NATIVE, EDITABLE loft (no STEP involved)
.venv/bin/python swexport.py --sections 25     # -> out/solidworks/sec*.sldcrv
.venv/bin/python swmacro.py                    # -> C:\Users\Ben\fpv250-sw\build_profiles.vbs
cmd.exe /c "cscript //nologo C:\Users\Ben\fpv250-sw\build_profiles.vbs"
#   builds 25 3D sketches, lofts them, reports body count + volume

# B. every solid as a part document, plus the assembly
.venv/bin/python swassembly.py --reference --symmetry
#   explodes assembly.step into 16 single-product STEPs, writes a manifest,
#   compiles swtool.cs, runs it, and asserts SolidWorks reproduces the
#   build123d volumes and centre of mass. --symmetry reports which 4-off
#   parts are genuine repeats.
```

Route A gives a feature tree you can edit; route B gives dumb solids but the
complete aircraft. They are complementary, not alternatives.

**Measured, this run** (params.yaml snapshot of 2026-09-10):

| quantity | value |
|---|---|
| Python model, spline loft through 25 sections | **188.928 cm³** |
| build123d rebuild, *ruled* loft through the 25 exported profiles | 187.778 cm³ (−0.61%) |
| **SolidWorks `InsertProtrusionBlend` through the same 25 profiles** | **188.398 cm³ (−0.28%)** |
| bodies produced | 1 solid |
| build time | 1200 segments in 137 s, plus the loft |

Worth reading carefully: SolidWorks' default loft is **not** purely ruled. It
lands between the ruled rebuild and the spline model, so it reproduces the real
body *better* than a linear interpolation would — which is why the profile
count, not the blend type, is the lever.

| assembly quantity | SolidWorks | build123d reference |
|---|---|---|
| total volume, 16 components | 120 295.14 mm³ | 120 299.78 mm³ (−0.004%) |
| centre of mass | (**−0.149**, 0.000, −0.927) mm | (**−0.149**, −0.000, −0.940) mm |
| component count | 16 | 16 |

The whole 4.64 mm³ of volume difference is the two cowls (§4.7): +6.32 and
−10.97 mm³, which sum to −4.65.

That X centroid of **−0.149 mm** is the number that matters. An earlier build
of this assembly — the one that placed the 4-off parts by rotation — gave
exactly **0.000**, because a rotationally-reconstructed airframe is
symmetric by construction. The model's is not. A checksum that can only ever
come out "perfect" is not a check.

The saved `.SLDASM` was then **closed and reopened** and re-measured — 16
top-level components, 120 295.14 mm³ — because "the in-memory document looks
right" and "the file on disk is right" are different claims.

**There are no mates in the assembly and there should not be.** Every part is
exported in body coordinates, so the components at the identity transform
self-assemble exactly — provided you overwrite `Transform2` yourself (§4.10).

**Do not assume you know how a 4-off part is repeated.** The model exports
element `[0]` of each list and `motor_stations()` orders them FL, FR, RL, RR,
so the exported instance is the front-left one — and the obvious economy is to
insert it four times at 0 / −90 / +90 / 180° about +Z. An earlier version of
this tool did exactly that and put **four components 11.8 mm out of place**,
with every scalar check passing at +0.000%.

Measured against the model's own `assembly.step`, de-translating each instance
before comparing:

| part | how the four instances actually relate |
|---|---|
| `nacelle_mount` | one part **translated** — all four agree to **7e-12 mm** once the translation is removed |
| `arm_tube` | one part, two translated and two rotated 90° about +Z |
| `arm_fairing` | two related exactly; the other two off by 1.3 mm — **a real model bug**, see below |

The nacelle is the instructive one, and it is instructive because the first
version of this section got it wrong. `nacelle_axis()` returns the same
`BORE_AXIS` at every station, so the four pods differ by **translation only** —
no rotation at all. The test that was meant to catch the bad placement compared
each instance against rotations about the origin, found nothing, and reported
the nacelles "unrelated". **A family of rotations about the origin cannot
express a pure translation.** The negative result bounded the candidate set,
not the design, and reading it as a fact about the design produced a confident
and wrong conclusion ("four distinct nacelle prints"). They are one part,
printed four times.

So always ask what hypothesis a test can actually reject, and compare
**de-translated** clouds when you want to know whether two things are the same
shape.

The fairing's 1.3 mm was the opposite case — a real defect, found only because
two independent representations of the same geometry were compared.
`sections.fairing_section()` was dropping the lower trailing-edge point, which
left `te_thickness` inert and the section asymmetric. Fixed upstream; chirality
fell to 0.125 mm. Neither representation's own validation caught it. **That is
the argument for keeping the SolidWorks path in the loop** — not the pictures,
the disagreement.

Note also that a mirror can never be a component transform: `Transform2` is a
rigid motion, determinant +1. A genuinely mirrored instance needs its own part
file however clever the placement logic gets.

#### Nothing cheap catches this

That mis-placed assembly shipped with **every check passing**:

| check | result with four components wrong |
|---|---|
| solid count per part | correct |
| part volume vs the OCCT source | +0.000% |
| assembly volume vs the sum of its parts | +0.000% |
| assembly centre of mass vs component transforms | agreed to 0.001 mm |
| the nacelle's own centre of mass | **0.0001 mm** from correct, with vertices **11.8 mm** out |

(The nacelle is nearly symmetric about its own axis, so displacing it barely
moves its centroid — which is precisely why a centroid check could not see an
11.8 mm error.)

A congruent solid in the wrong place, and a mirror image, both preserve volume
and bounding box, and a nearly-symmetric part preserves the centroid too. The
only test that has not lied here is the **worst nearest-vertex distance**
between two vertex clouds: 0.000000 mm for the right candidate, 10.9–130 mm for
every wrong one.

It has to be *nearest-neighbour*. Sorting both vertex lists and comparing them
elementwise does **not** work: coordinate sets that agree to a micron sort
differently when vertices are near-tied in X, the comparison then pairs the
wrong points, and it reports tens of millimetres of error between two shapes
that coincide exactly.

```python
import numpy as np
def shape_distance(a, b):           # a, b: (n,3) vertex clouds
    if len(a) != len(b): return float("inf")
    d = np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2)
    return float(d.min(axis=1).max())
```

#### So do not infer placement at all

`assembly.step` already contains every instance in its final position.
`swassembly.py` explodes it into one single-product STEP per solid and inserts
each at the identity transform: nothing derived, nothing assumed, 16 components
and 16 part files. `--symmetry` still reports how the repeats relate — it just
no longer decides anything, which is the only reason it being wrong once was
survivable.

The cost is a flatter tree: four nacelle documents rather than four instances
of one. Worth revisiting if the assembly ever needs a real BOM, because the
nacelle and the tube are both genuine repeats.

The **arm tube** is the part that
physically locates everything else and is the one you would instinctively
reach for a mate to place. It needs none. The core body is genuinely bored —
`core_body & arm_tube` measures 0.000 cm³ in build123d — so the tube at its
correct transform slides into its own bore with no interference, and a
concentric mate would only add a redundant constraint that can later conflict.
**If the parts already carry their position, mates are not a convenience, they
are a liability.**

---

---

## 8. Measuring the PART, not just the assembly (2026-09-12)

§7 verifies that the assembly is the right set of solids in the right
places. It says nothing about whether a solid has a hole in it. Four
questions came up the same day — is the nose closed, is the camera bore a
real through hole on the boresight, does the nacelle cone end in a
printable flat, is the arm fairing the right way round — and none of them
is answerable from volume, bounding box or centre of mass.

All four are answerable from topology and temp-body booleans, and all four
were cross-checked against build123d. The tool is `design/swtool.cs`'s
sibling, staged as `cs/swverify.cs`.

### 8.1 "Is it open?" is a question about LOOPS, not area

A truncated loft that has been capped is a planar face with **one** outer
loop. The same face before capping is an annulus: one outer loop and one
inner. A face with a bore through it has one outer loop and one inner loop
*per hole*. So the openness test is:

```csharp
ISurface s = (ISurface)f.IGetSurface();
if (s.IsPlane()) {
    double[] pp = (double[])s.PlaneParams;   // 0-2 normal, 3-5 root point
    // ... select the face at the truncation plane ...
}
ILoop2 l = (ILoop2)f.GetFirstLoop();
while (l != null) { if (!l.IsOuter()) inner++; l = (ILoop2)l.GetNext(); }
```

`IFace2.GetArea()` is m²; `PlaneParams[3..5]` is the root point in metres.
`ISurface.CylinderParams` is `[0..2] root, [3..5] axis, [6] radius`, and
`ConeParams` starts the same way — which is how "the bore is on the
boresight" becomes a number (`axis · boresight = 1.000000`) rather than an
impression.

Counting **inner loops is strictly better than comparing areas**, because
it does not need a reference area. The area comparison here needed the
full section area of the nose, and the analytic superellipse (2000 points)
is 418.280 mm² while the loft's actual 56-segment section is 418.250 —
0.03 mm² of pure discretisation bias sitting in the answer.

### 8.2 Temp-body probes beat ray casting

`RayIntersections` is the obvious instrument for "is there material along
this line" and it faulted (§5). The replacement measures the same thing and
returns a **volume**, which is a better answer than a hit list:

```csharp
IModeler mod = (IModeler)sw.IGetModeler();
double[] cyl = { bx, by, bz, ax, ay, az, radius, height };   // metres
IBody2 tool = (IBody2)mod.CreateBodyFromCyl((object)cyl);
IBody2 copy = (IBody2)body.Copy();          // Operations2 CONSUMES the body
int err = 0;
object res = copy.Operations2((int)swBodyOperationType_e.SWBODYINTERSECT,
                              (object)tool, out err);
double[] mp = (double[])((IBody2)r).GetMassProperties(1000.0);
double mm3 = mp[3] * 1e9;                   // index 3 is VOLUME, in m^3
```

Notes that cost time:

- `Copy()` first. `Operations2` consumes the target body.
- `out err`, not `ref err` — the interop signature is `out`.
- `swBodyOperationError_e.swBodyOperationNoIntersect = 1067` is the "clean
  miss" code; a null / empty result is also a legitimate zero.
- **Check the index of `GetMassProperties` against something you already
  know.** `mp[3] * 1e9` on the whole cowl returned 14 982.25 mm³, which is
  the number the assembly check had already printed. That is one line and
  it removes an entire class of silent off-by-one.

### 8.3 A negative probe proves nothing without a positive control

The camera-bore test is "0 mm³ of material along the boresight". An empty
result is exactly what a probe that is aimed at nothing, or oriented
backwards, or built with a zero-length cylinder also returns.

The first version of the **build123d** cross-check ran its sample line
along `tip + boresight * t` with `t` from −1 to +30 — the boresight points
**outward**, so it sampled from 1 mm *inside* the nose to 30 mm *out in the
air*. It reported `0/62`, the expected answer, for entirely the wrong
reason, and it would have reported `0/62` on a nose with no bore at all.

Two controls caught it and both are now permanent:

| control | as built | rebuilt with `aperture_dia = 0` |
|---|---|---|
| probe on the boresight | **0.0000 mm³** | 3/62 samples in material |
| same probe 7.5 mm off-axis | **9.1301 mm³** | 3/62 |
| inner loops on the nose face | **1** | **0** |
| nose face area | 244.34 mm² | 418.25 mm² |

The off-axis probe is the one that matters: it proves the instrument can
see material that *is* there, on the same part, in the same run. Rebuilding
the model with the feature switched off is the other half — and it is free,
because a parametric model can always be asked the counterfactual.

### 8.4 Orientation, and what a section test can actually reject

"Max thickness 34% aft of the leading edge" needs a chord direction, and
the chord direction comes from the model. Feeding the model's own frame
back in would make the test circular — so split it:

- **the model supplies the frame** (chord, thickness and span unit vectors,
  plus the freestream);
- **SolidWorks supplies the shape**, tessellated off its own re-knitted
  B-rep via `IFace2.GetTessTriangles(true)` (metres), projected onto that
  frame and binned along the chord.

That rejects the hypothesis the 2026-09-09 bug was an instance of — a
section swept in the wrong sense, which reads 65.6% instead of 34.4% — and
it rejects a mirrored or reversed part. It does **not** test the trim
pitch: both representations share that scalar, so a wrong trim angle would
move the "correct" answer in both at once. State that rather than let
"34.4%, confirmed independently" imply more than it does.

Bin the chord and report the **centre of the plateau**, not the first bin
that attains the maximum. A 41 mm chord in 80 bins has a flat maximum
several bins wide; `argmax` picked 32.5% in build123d and 34.4% in
SolidWorks for the same shape purely by tie-breaking.

### 8.5 Leaving the view set is also a measurement

`ShowNamedView2` **animates**, and the animation advances on SolidWorks'
idle time, not on the call. Six separate attaches read six different
orientations — `(-0.754, -0.127, 0.645)`, `(-0.961, -0.072, 0.267)`,
`(-0.440, 0.119, 0.890)` — before it settled at `(0.5774, 0.5773, 0.5774)`.
Within any one process the value was rock steady, which makes it look like
a stable wrong answer rather than a moving one.

Also: pass the standard-view **id with an empty name**.
`ShowNamedView2("*Isometric", swIsometricView)` supplies both and did not
land; `ShowNamedView2("", (int)swStandardViews_e.swIsometricView)` did.
And `IModelView.DisplayMode` is 4 for shaded, **5 for shaded-with-edges** —
`ViewDisplayShaded()` was observed to be overridden back to 5 on the next
activation, so set `v.DisplayMode` explicitly and read it back.

### 8.6 Two guards fired this run, and both were right

**The sliced-mass record.** `sliced_mass.json`'s fingerprint matched
(`design_vars` had not moved) but `swassembly.py` still refused:

```
cowl_fwd: regenerated volume 14995.73 mm3 disagrees with the sliced
record's 15069.57 mm3 by -0.490% even though the fingerprints match
-- do not trust either
```

Correct, and it is the §4.9 warning working exactly as written: the
fingerprint hashes *parameters*, and the geometry had moved because
`frame/model.py` changed after the slice — the camera aperture became a
real through bore. The other four printed parts matched to **+0.000%**,
which localises the change to one part without any diffing. The run was
redone `--geometry-only`; no mass is reported, which is the right answer,
because the alternative is a confident wrong one.

**The solid-naming heuristic.** `explode_assembly()` names each solid in
`assembly.step` by matching its volume to a per-part export within 0.1%,
and today's nacelle change moved `nacelle_mount` to 8601.72 mm³ — **5.49
mm³** from `arm_fairing`'s 8596.24, inside the 8.60 mm³ window. Every pod
matched *two* buckets and the run aborted:

```
solid of volume 8601.72 mm3 in assembly.step matches 2 known parts,
need exactly 1
```

Aborting was right; the window is not. "Within tolerance of exactly one"
fails as soon as two parts happen to be a similar size, which is a
coincidence and not an error. Assign to the **nearest** volume and then
confirm the assignment with the de-translated nearest-vertex distance
(§6) — which came back 0.000000 mm for all three repeated parts. That is a
check that gets *stronger* as parts get more alike, where the volume window
gets weaker.

### 8.7 Measured, this run (params.yaml of 2026-09-12, trim 75.219°)

| quantity | SolidWorks | build123d |
|---|---|---|
| assembly, 16 components | **126 519.76 mm³** | 126 545.66 mm³ (−0.0205%) |
| centroid | (−0.154, 0.001, 0.567) mm | (−0.154, −0.000, 0.567) mm |
| `cowl_fwd` | 14 982.25 mm³ | 14 995.73 (−0.090%) |
| `cowl_aft` | 13 356.95 mm³ | 13 369.41 (−0.093%) |
| everything else (14 parts) | — | +0.000% |

The whole −25.90 mm³ is the two spline cowls, and the two deltas sum to
−25.94 — the same re-knitting budget §4.7 records, except that this time
**both** went the same way (2026-09-10 was +0.046% / −0.083%). So the sign
is not a property of the part; do not build a correction out of it.

| check | SolidWorks | build123d |
|---|---|---|
| planar faces at the nose truncation | 1 | 1 |
| inner loops on it (= openings) | **1** | **1** |
| nose material area | 244.343 mm² | 244.273 mm² |
| nose open area | 173.94 mm² | 174.01 mm² |
| bore cylinder radius / axis·boresight | 5.5000 mm / 1.000000 | 5.5 mm / 1.0 |
| material on the boresight, 1 mm proud → 30 mm in | **0.0000 mm³** | **0/62 samples** |
| same probe 7.5 mm off-axis (control) | 9.1301 mm³ | 3/62 samples |
| nacelle tip flat | 0.6362 mm² → **⌀0.9000 mm**, normal +Z | ⌀0.9000 mm, normal +Z |
| nacelle pod z-extent | [−23.800, +19.500] mm | [−23.800, +19.500] mm |
| prop clearance | 3.000 mm | 3.000 mm |
| fairing chord / max thickness | 41.000 / 12.888 mm | 41.000 / 12.847 mm |
| max thickness aft of LE | **34.4%** | 34.4% (plateau centre) |
| chord · flight direction | −0.9836 (LE upstream) | −0.9836 |

---

## 8.8 Reviewing a parameter study before the solver runs it (2026-09-12)

Six geometry variants of a CFD A/B (`design/mergeab.py`'s `CASES`) were built
from a frozen snapshot of `frame/` and imported for a look **before** solver
time went into them. Generators: `design/out/swreview/` (`build_variants.py`
exports the STEPs and measures them in build123d, `swreview.cs` imports and
measures them in SolidWorks against those numbers).

Three of the instruments written for it were wrong before the geometry was,
which is the part worth keeping.

### The silhouette scan -- one number for "is there a kink in the nose"

A body of revolution built by revolving a **polyline** is one conical face per
segment, so `r(z)` is exactly linear on each face and a slope break between
neighbouring faces is a real crease, not discretisation. Tessellate each face
(`IFace2.GetTessTriangles(true)`, metres), convert to `(z, r)` about the known
axis, least-squares fit, sort by `z`, and difference:

```
worst |ang(i) - ang(i+1)|   over the bands inside the nose window
```

Measured, and agreeing to 0.01 deg with the same scan run on OCCT's own faces:

| pod | last profile band | next band | break |
|---|---|---|---|
| spliced (power cap grafted on) | -52.870 deg | -26.581 deg | **26.29 deg** |
| continuous (Bezier to the tip) | -48.870 deg | -49.846 deg | **1.10 deg** |

The 26.3 deg figure in `frame/model.py`'s own comment is therefore not an
estimate -- two independent representations reproduce it.

### An axis-parallel hole reads as a 15 deg kink unless you filter for it

The first run of that scan reported the *continuous* nose breaking by **14.93
deg at z=8.185**, which is 13.8 deg worse than build123d said. Neither was
wrong about the pod: the scan had swallowed the **M2 bolt-hole cylinders**,
which are parallel to the pod axis but offset 8.485 mm from it, so their `r`
scatters with azimuth and the fit returns ~0 deg, next to a band at -14.9 deg.

The filter is free and it is principled: on a surface of revolution the fit
residual is zero. Reject any face whose RMS residual exceeds 0.02 mm and report
how many you rejected -- four, every time, which is itself the count of bolt
holes reaching into the nose window.

> **A band table is not a meridian unless you have checked that every band is
> axisymmetric.** The build123d version of the same scan never saw this,
> because it sampled `BRepAdaptor_Surface.Value(u, v)` over the face's
> parameter box -- which ignores the trim, so a face with a hole punched in it
> samples as if the hole were not there. Two representations disagreed by
> 13.8 deg and *both* were reporting something true.

### `GetTwoAdjacentFaces2` cannot be used to count free edges

The obvious watertightness test -- walk `IBody2.GetEdges()`, call
`IEdge.GetTwoAdjacentFaces2()`, count the edges with fewer than two faces --
reported **78 to 257 free edges on all 18 bodies**, including bodies whose
volume matched build123d to +0.000% and which OCCT's `BRepCheck_Analyzer` calls
valid closed solids. A **seam** edge of a periodic face has the same face on
both sides and comes back as one.

What SolidWorks will actually tell you is the body *type*: an unclosed shell
arrives as a **sheet** body, not a solid one.

```csharp
Array solids = pd.GetBodies2((int)swBodyType_e.swSolidBody, true) as Array;
Array sheets = pd.GetBodies2((int)swBodyType_e.swSheetBody, true) as Array;   // must be 0
```

### `BRepExtrema_DistShapeShape` is a distance, not a containment test

A point *inside* a solid is not at distance 0 from it: `DistShapeShape`
measures to the solid's **faces**, so an interior point returns its distance to
the nearest wall and a `d < 1e-9` "inside" test answers `False` everywhere
except exactly on the skin. It silently produced "the skin passes inside the
bolt circle at z=0.000" for every variant -- z=0.000 being simply the first
sample. Use the classifier:

```python
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.TopAbs import TopAbs_State
c = BRepClass3d_SolidClassifier(solid.wrapped, gp_Pnt(x, y, z), 1e-7)
inside = c.State() == TopAbs_State.TopAbs_IN
```

`DistShapeShape` is still the right tool for the question it answers -- the
minimum gap between two solids, which is how a 0.100 mm fairing-to-pod slot was
measured on this same run.

### Inner loops cannot see an opening that spans several faces

§8.1 counts inner loops to find holes, and that is right for a hole that sits
inside one face. The four bolt holes break out through the pod's **flank**,
which the revolve has split into ~55 narrow conical bands -- so the opening
crosses ten of them, modifies their *outer* loops, and adds no inner loop
anywhere. SolidWorks and build123d agreed exactly: **6 inner loops, all of them
on the two planar faces at z=-23.800 and z=-6.600**, and none on the flank, on a
part that demonstrably has four holes in its flank.

Classify points instead, and **pick the control azimuth by looking at the bolt
pattern**. The first control was "90 deg away from the bolt", which on a
four-bolt square pattern at +/-45 deg is *another bolt* -- it duly reported a
hole, and the control looked like it had failed the part. 45 deg off is between
bolts:

| probe, at the bolt-hole radius just under the skin | envelope | printed part |
|---|---|---|
| on the bolt azimuth | IN | **OUT** |
| 45 deg off, between bolts (control) | IN | **IN** |

### What the review found in the geometry

| finding | number |
|---|---|
| every variant: one closed solid, SolidWorks vs build123d | +0.000% on the parts, -0.052 to -0.055% on the six `cfd_surface` bodies (spline re-knitting, §4.7) |
| `cont` nose kink | 26.29 deg -> **1.10 deg** |
| nacelle tip flat, both modes | 0.6362 mm2 = dia 0.9000 mm, normal +Z |
| fairing-to-pod gap | **0.100 mm in all six** -- `flare_tip` scales thickness, the gap is spanwise, so the flare cannot close it |
| loft (11 sections) vs the extrude it replaced, at flare 1.0 | +0.000000% volume, worst nearest-vertex **6.4e-8 mm** |
| arm fairing vs the prop disc | +0.048 mm clear at baseline, **-0.008 to -0.063 mm (inside)** on every flared variant |

`geomcheck.check_prop_clearance()` tests only the nacelle pod, and against the
*profile* rather than the placed solid. The arm fairing is not tested against
the prop disc at all.


## 8.9 Building the PRINTED parts and the AERO ENVELOPE side by side (2026-09-12)

`M.build(p)` and `M.cfd_surface(p, pitch)` are two different solids and they
are supposed to differ. `cfd_surface` is built with `solid=True`, which
returns **before** the motor pocket, the boss bore and the bolt holes are cut,
and it seals the camera aperture to a blind recess. A review that imports only
`cfd_surface` therefore shows a pod with a solid back end and no bolt pattern,
and there is no way to tell from the screen whether that is the CFD
simplification or a modelling defect. It happened, and the defect report that
came back was about the envelope, not the part.

So export **both**, and name them so nobody has to remember which is which:

```
core_body_printed.SLDPRT  cowl_fwd_printed.SLDPRT  ...   <- M.build(p)
aero_envelope.SLDPRT                                     <- M.cfd_surface(p, pitch)
```

`design/out/swcad5/build_parts.py` + `swcad5.cs` do exactly this.

### Five ways this pipeline lies to you, and what each one looks like

**1. `SaveAs` returns error 1 for every part, silently, and the run measures
geometry it never wrote.** The documented cause is an open assembly holding
its components (§4.9). There is a second cause and it is easier to hit: a
document with the same **TITLE** is already open. After a run that imported
and then failed, the imported documents are still open with an **empty path**
and the target's title — so a cleanup that closes "everything under my parts
directory" closes none of them. Match on title as well as path:

```csharp
string bare = ti.EndsWith(".SLDPRT", StringComparison.OrdinalIgnoreCase)
            ? ti.Substring(0, ti.Length - 7) : ti;
```

**2. Reopening a part you just imported and saved returns `null` with
`err=65536`.** That is *file with the same title already open*, not *file not
found*, and `LoadFile4` leaves the document open after `SaveAs`. Either keep
the `IModelDoc2` reference or `QuitDoc` it first and reopen from disk.

**3. Holding every imported document open through the import loop kills
SLDWORKS.exe.** Eight open imports and the next `LoadFile4` came back as
`COMException 0x800706BE (RPC failed)` with the process gone. Import → measure
→ `SaveAs` → `QuitDoc`, one document at a time, and reopen the two or three
that need detailed measurement.

**4. Two COM clients on one SLDWORKS.exe take it down.** This run shared the
machine with another tool driving the same instance; SolidWorks died inside
`LoadFile4` five times. The evidence is not in any SolidWorks output — it is in
the Windows Application log:

```powershell
Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='Application Error'} -MaxEvents 5
#  Faulting application name: SLDWORKS.exe ... Faulting module name: mfc140u.dll
#  Exception code: 0xc0000005
```

Read that log before blaming your STEP: a file that imported cleanly ten
minutes earlier crashed the process on the next attempt, which is what
finally identified the contention. `tasklist` for other tooling, and check
whether **two** SLDWORKS.exe are running — only one can be in the ROT, and
`Marshal.GetActiveObject` gives you whichever registered.

A retry wrapper is the only thing that gets a contended run finished:
relaunch the EXE (never `CreateObject` — that instance can never be reached),
wait for the ROT, run again. `design/out/swcad5/run_asm.py` is a 40-line
example; it took **five** attempts.

Related, and it looks unrelated: `csc` failing with *"Could not write to output
file 'swtool.exe' — the process cannot access the file"* means an **orphaned
`swtool.exe` from a killed run is still attached to SolidWorks**. `taskkill`
it; the next compile then succeeds.

**5. The SAME crash signature with only ONE client: a missing `[STAThread]`
(2026-09-25).** Item 4 says two COM clients produce the `mfc140u.dll` /
`0xc0000005` fault. They do — but so does an apartment mismatch, and then you
hunt for a second client that does not exist. A C# console `Main` defaults to
the **multi-threaded apartment**; SolidWorks is an **STA** server, so every
call from an MTA client is marshalled through a proxy that depends on the
server's message pump. It works until it doesn't.

What it looks like, measured on the run that found it — the first import after
the pod changed and `assembly.step` went 15 → 76 MB:

| | |
|---|---|
| `LoadFile4` | returned; `core_body.SLDPRT *` showed in the title bar |
| then | **both processes went to zero CPU and stayed** — `swtool` 0.06 s total, SLDWORKS 0.03 s per 10 s of idle tick |
| dialogs | **none**, confirmed by enumerating every visible top-level window system-wide and by class `#32770` specifically |
| `parts/` | empty — the `SaveAs` never ran |
| after killing the client | the RPC channel was broken: next `LoadFile4` → **`0x800706BE`**, taking SLDWORKS.exe down with the `mfc140u.dll` fault |

**Zero CPU on both sides is the tell.** Slow work burns CPU somewhere; a
deadlock burns none. Check that before reaching for the contention
explanation, and check the client's apartment before blaming the geometry:

```csharp
[STAThread]                     // <- on Main, in every SolidWorks client
static int Main(string[] args)
```

`swtool.cs` and `swverify.cs` both carry it now. Both had run for weeks
without it, which is the point — an apartment mismatch is intermittent, and it
gets worse as call volume and geometry complexity grow.

### `ISurface::ConeParams` — the axis sign is not usable, so measure the face

`ConeParams` returns `[0-2] root, [3-5] axis, [6] radius at the root, [7] half
angle`. It does **not** tell you which way the radius grows in any form you can
trust: taking the reported axis at face value put the camera flare's mouth at
**9.50 mm**, reversing it put the same face at **12.50 mm**, and the arithmetic
cannot decide between them. Both are plausible numbers for this part. Measure
the face instead — tessellate it, express every vertex as (distance along the
bore axis from the nose tip, distance from that axis) and least-squares fit:

```csharp
Array tess = f.GetTessTriangles(true) as Array;      // IFace2, not IBody2
// ... r = a + b*s  ->  a is the radius at s = 0, b is tan(half angle)
```

Measured on the adopted cowl: `r = 6.2500 + 0.250000*s`, i.e. **Ø12.5000** at
the nose-tip plane and a half angle of 14.0362° — matching `ConeParams[7]`
exactly, which is how you know the fit is reading the right face.

### A revolve makes the profile's slope directly measurable

`nacelle_mount` is a revolve of an 80-point polyline, so SolidWorks holds it as
**79 conical faces**, one per profile segment. `ConeParams[7]` on each is that
segment's half angle, and sorting the faces by z gives the profile's slope
sequence straight off the model. The successive difference is then a
kink detector with no reconstruction in it at all:

| build | largest step between adjacent faces |
|---|---|
| spliced profile + power cap | 26.29° at the graft |
| `profile_mode: continuous` (adopted) | **1.1005°**, i.e. pure discretisation |

Two faces that are not cones would mean the nose is not what you think it is.

### `IBody2` has no `GetArea`

Surface area of a body is `GetMassProperties(rho)[4]`; `[3]` is volume, `[0-2]`
the centre of mass. `GetArea()` exists only on `IFace2`. (C# turns this into a
compile error, which is the whole argument for early binding.)

### `ActivateDoc3` is another `[in,out] long*` — unreachable from VBScript

So "bring the assembly to the front" cannot be done the obvious way, and
`OpenDoc7` on a document that is **already open** returns it without
activating — `ActiveDoc` then still reports whatever was opened last. The
VBScript-only route is to close it and open it again:

```vb
swApp.QuitDoc "fpv250_frame.SLDASM"
Set d = swApp.OpenDoc7(swApp.GetOpenDocSpec(path))   ' now it IS the front window
```

### Point-in-solid, on the build123d side, is the cheapest second opinion

For "does this hole break out", a kernel classifier beats any boolean:

```python
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.TopAbs import TopAbs_State
c = BRepClass3d_SolidClassifier(shape.wrapped, gp_Pnt(x, y, z), 1e-7)
inside = c.State() == TopAbs_State.TopAbs_IN
```

March it along the hole axis and it reports where material starts and stops,
which is a stronger statement than "0 mm³ was removed above z=0". Its one
gotcha: a scan window chosen from the *nominal* hole top finds nothing when a
different feature (the boss bore) already cleared that column — start the scan
below the body and end above it.

Equally: a face bounding box is **not** a point on the axis. The bolt columns'
`bbox.max.Z` read 12.703 mm while the printed part's material on the axis ran
to 10.902 mm; both are right, because the highest point of a 2.2 mm column
through a curved pod is on the column's edge, not its centre line.

---

## 8.10 Filleting a junction that OCC cannot blend (2026-09-12)

**The question:** build123d's `fillet()` tops out at 0.3 mm on the arm
fairing's junctions, and CFD wants 1-3 mm. Can SolidWorks do it **entirely by
script** -- import, boolean, select the edges programmatically, fillet, export
STL -- so it becomes a stage in the CFD pipeline rather than a review tool?

**Answer: yes, with one condition on the geometry.** A single scripted
invocation runs import -> Combine -> programmatic selection -> two fillets ->
watertight binary STL in **15.5 s wall clock**, no human in the loop.
Generators: `design/out/swfillet/` (`build_parts.py`, `occ_control.py`,
`stlcheck.py`, `swfillet.cs`).

### The control: what OCC does on exactly the same body

Same overlapping solids (fairing extended 3 mm into both neighbours, so no
assembly clearance is in the aero surface), same edge sets, `build123d.fillet`:

| junction | edges | 0.1 | 0.2 | 0.3 | 0.4 | 0.5 | 1.0 | 2.0 | 3.0 mm |
|---|---|---|---|---|---|---|---|---|---|
| fairing-body | 5 / 90.8 mm | fail | **ok** | **ok** | fail | fail | fail | fail | fail |
| fairing-nacelle | 112 / 78.5 mm | fail | fail | fail | fail | fail | fail | fail | fail |

The 0.2/0.3 successes matter more than the failures: they are the positive
control proving the edge selection and the harness are sound before anything
is claimed about SolidWorks.

### What SolidWorks does

Measured on the same imported bodies, each trial on a freshly re-opened copy
of the combined part so trials cannot contaminate one another.

| junction | method | 0.5 | 1.0 | 2.0 | 3.0 mm |
|---|---|---|---|---|---|
| fairing-body (5 edges) | constant radius | fail | fail | **+36.499** | **+76.045** |
| fairing-body | variable radius, all poles equal | **+3.880** | **+10.926** | **+38.307** | **+76.266** |
| fairing-nacelle (112 edges) | constant **and** variable | fail | fail | fail | fail |
| fairing-nacelle, **spline pod** (6 edges) | constant | **+10.454** | **+33.417** | fail | fail |
| fairing-nacelle, **spline pod** | face fillet | -1.108 | -4.373 | **+12.052** | **+25.210** |

dVol in mm3, each verified as one solid body, zero sheet bodies, `Check2()==0`.
With `fairing.chord` +10% every number moves but the pattern does not:
variable radius still succeeds at all four radii on the body junction
(+12.029 / +25.828 / +49.907 / +92.455).

**So SolidWorks reaches 3 mm where OCC reaches 0.3 -- a factor of ten -- on a
junction OCC calls impossible at 0.4.**

### `swFeatureFilletType_VariableRadius` with equal radii beats the constant fillet

Constant radius fails at 0.5 and 1.0 and then succeeds at 2.0 and 3.0. That
non-monotonicity is reproducible and is not a selection artefact -- the same 5
edges are selected every time. Passing the *same* radius through the
variable-radius path succeeds at **every** radius:

```csharp
double[] ra = new double[es.Count];
for (int k = 0; k < ra.Length; k++) ra[k] = R / 1000.0;
f = doc.FeatureManager.FeatureFillet3(
        (int)swFeatureFilletOptions_e.swFeatureFilletVarRadiusType,
        R / 1000.0, 0.0, 0.0,
        (int)swFeatureFilletType_e.swFeatureFilletType_VariableRadius,
        (int)swFilletOverFlowType_e.swFilletOverFlowType_Default,
        (int)swFeatureFilletProfileType_e.swFeatureFilletCircular,
        (object)ra, null, null, null, null, null, null) as IFeature;
```

It is not the same surface -- +38.307 against +36.499 mm3 at R=2 -- so it is a
genuinely different blend, not a different route to the same one. Treat it as
the default and constant radius as the fallback, which is the opposite of the
usual advice. `swFilletOverFlowType_KeepSurface` changed nothing on either
junction; it is not the lever.

### Selecting the edges: classify FACES by ownership, then take the edges between

No IDs, no rays, no clicking. Before the boolean, the three imported bodies are
the oracle; after it, every face of the merged body still lies on exactly one of
their surfaces.

1. For each face of the merged body take a point that really is on it --
   the centroid of its **largest** tessellation triangle, pulled back with
   `IFace2.GetClosestPointOn` (a curved triangle's centroid is off the surface).
2. Distance from that point to each original body = min over that body's faces
   of `GetClosestPointOn`. Under 1e-6 m means the face lies on that body.
3. A junction edge is one whose two `GetTwoAdjacentFaces2()` have **different**
   owners. Index the faces by `Marshal.GetIUnknownForObject` -- `IFace2` has no
   `GetID`, and COM identity is what you actually want.

Measured, this partitions cleanly and survives a shape change:

| | base | chord +10% | spline pod |
|---|---|---|---|
| merged faces | 144 | 144 | 12 |
| fuselage-only / fairing-only / nacelle-only | 4 / 6 / 134 | 4 / 6 / 134 | 4 / 6 / 2 |
| **ambiguous or unowned** | **0** | **0** | **0** |
| fairing-body edges (build123d says 5) | 5 | 5 | 5 |
| fairing-nacelle edges | 112 (b3d 112) | 112 (b3d 112) | 6 (b3d 6) |

The same unmodified code found the right edges on all three. That is the
difference between a pipeline stage and a manual step, and it is the reason to
prefer this over `SelectByRay` or a stored edge ID.

A second, independent selector -- "edges within 1 um of the junction sample
points build123d exported" -- was run as a cross-check. It agreed exactly on
five of six cases and returned **114 instead of 112** on the chord+10% pod.
Proximity selection is tolerance-sensitive at a shattered junction; adjacency
is not. Use adjacency, keep proximity as the cross-check.

### The blocker was the pod's POLYLINE revolve, not the blend

`nacelle_mount()` revolves `nacelle.profile()` as a `Polyline`, so the pod is
one conical band per profile segment: **81 faces, 134 on the merged body, and a
fairing/pod junction shattered into 112 edges averaging 0.7 mm.** No edge-based
fillet of any kind succeeded on it, at any radius, in either geometry.

Rebuild the identical profile as a `Spline` revolve -- same pod to +0.001%
volume, 16 237.516 against 16 237.350 mm3 -- and the junction becomes **6 edges
over the same 78.47 mm**. Constant radius then works at 0.5 and 1.0, the face
fillet at 2.0 and 3.0, and **both junctions fillet on the same body at once**:
variable radius 3.0 mm on the body junction plus a 2.0 mm face fillet on the
pod, one solid, 5 new blend faces totalling 394.104 mm2.

`_section_wire`'s docstring already records this for the fairing ("121 faces
... which no fillet can span") and `fuselage.section_curve: spline` already
fixes it for the body (56 strips -> 1 face). **The pod is the one that never
got the option.** That is the actionable finding: a `nacelle.profile_curve:
spline` would be the cheapest possible unlock.

### Only ONE junction can be filleted per body without it

On the 112-edge pod, whichever junction is filleted first succeeds and the
second then fails **at every radius on a 3.0/2.0/1.0/0.5 ladder, in both
orders** -- and for the body junction the selection is still perfect (5 edges,
5 selected) when the fillet returns null. Whether that is a geometric
limit or a feature-manager artefact is **not resolved here**; on the spline
pod the question does not arise, because both succeed.

### `InsertCombineFeature` for ADD takes a NULL main body

This cost an hour. `InsertCombineFeature(int OperationType, Body2 MainBody,
object ToolBodies)` reads like Common/Subtract, and passing a main body plus a
tool list is how those work. For **`SWBODYADD` the main body must be `null` and
every body goes in `ToolBodies`**:

```csharp
Body2[] all = ...;          // ALL THREE, not "the two tools"
IFeature comb = doc.FeatureManager.InsertCombineFeature(
    (int)swBodyOperationType_e.SWBODYADD, null, (object)all) as IFeature;
```

Symptoms of getting it wrong, both silent: a main body plus a **two**-element
tool array returns a real `CombineBodies` feature and leaves **two** solids;
a main body plus a **one**-element array returns **null** and leaves three.
Neither raises. Count the bodies.

Two more preconditions:

- **The imported document must be the ACTIVE one.** `LoadFile4` activates it,
  but another COM client can steal focus between calls, and then Combine
  returns null. Call `ActivateDoc3` and read `sw.ActiveDoc` back.
- The result matched build123d's own fuse to **-0.097%** on all three
  variants, which is the spline re-knitting budget of 4.7, not an error.

### A three-product STEP imports as a multi-body PART

§4.8 says SolidWorks decides part-vs-assembly from the file and you cannot
override it. The useful corollary: **several root products with no
`NEXT_ASSEMBLY_USAGE_OCCURRENCE` open as one part with several solid bodies**,
which is exactly what Combine needs. Call `Transfer` once per solid on one
`STEPControl_Writer`:

```python
w = STEPControl_Writer()
for sol in (fuselage, fairing, nacelle):
    w.Transfer(sol.wrapped, STEPControl_StepModelType.STEPControl_AsIs)
w.Write(dst)          # 3 PRODUCT, 0 NEXT_ASSEMBLY_USAGE_OCCURRENCE
```

Transfer a build123d `Compound` and you get one product per compound, not per
solid -- `_fuselage_solid()` returns a Compound, so take `.solids()[0]` first.

### Four instruments were wrong before the geometry was

**1. The STL exporter writes only the SELECTION.** The first export came back
16 769 triangles, **30 867 mm3** against an expected 229 822, and **179
unpaired edges**. Nothing was wrong with the fillet: 140 faces were still
selected from the previous call, and SolidWorks' STL translator quietly
exported those faces alone -- an open sheet whose bounding box (x 8.4..58.7)
is the fairing and pod with the fuselage missing. `ClearSelection2(true)`
immediately before `SaveAs`. The bounding box is what diagnosed it; the volume
alone would have read as a units bug.

**2. Edge arc length from `GetCurveParams2()[6..7]` over-reads on conics by
63%.** The fairing/pod junction measured 128.172 mm where build123d said
78.478. The same code on the spline pod gave **78.470 against 78.472** -- so it
is not a general bug: the 112 shattered edges are arcs of periodic conical
bands and the parameter range integrated is the full period, not the trim.
Edge *counts* from two independent selectors agreed at 112 throughout, so the
selection was right the whole time and only the ruler was lying.

**3. "A feature came back and the volume changed" is not "the fillet is
right."** The face fillet reported SUCCESS at all four radii on the chord+10%
body -- with **identical** volume changes for two *different* junctions
(-1.7970 vs -1.7990, -7.1586 vs -7.1702, -56.9148 vs -56.9148 at R=3). Two
different face-set pairs cannot produce the same geometry. Face set 1 (the
fairing, 6 faces) is common to both, so `FeatureFillet3` was evidently blending
set 1 against the body and ignoring set 2. **Every face-fillet number in this
section is therefore weaker evidence than the edge-based ones**, and the
face-fillet route should not be trusted without checking where the blend
landed.

The check that does work is to re-run the ownership classifier afterwards:
a face on **neither** original surface is new blend geometry. Base body,
variable radius 3.0 mm: **5 blend faces, 321.233 mm2** over an 88.841 mm
junction = 3.617 mm of arc, i.e. 69 deg subtended at R=3, i.e. a 111 deg
dihedral -- which predicts 68.2 mm3 of added material against the 76.266
measured. Self-consistent to 12% on a junction whose dihedral varies along its
length, which is the whole reason OCC could not blend it.

**4. `Extension.SaveAs` to STL wrote a DIFFERENT document's contents.** One
export produced sixteen files -- `base - arm_fairing_1-1.STL`,
`base - core_body-1.STL`, ... -- at the path asked for `comb_base.stl`. Those
are the components of the *other* agent's `fpv250_frame` assembly: it had
activated its own document between two of my calls, and the STL translator
followed the **active** document, not the `IModelDoc2` the call was made on.
Same root cause as the crashes below. Activate explicitly, and check the file
you got back is one file.

**5. `OpenDoc7` on an already-open path returns the IN-MEMORY document.** A run
that left the filleted body open made the next run "re-import and combine"
and then measure its starting volume as 229 822.310 -- the *filleted* value --
and find 0 junction edges. Walk `sw.GetDocuments()` and `QuitDoc` anything
under your staging directory before you start.

### Concurrency: two COM clients will crash SolidWorks, repeatedly

Another agent was driving the same SolidWorks over COM during this run. The
symptom is a hard process kill:

```
Faulting application: SLDWORKS.exe 32.3.1.2
Faulting module:      mfc140u.dll
Exception code:       0xc0000005     (access violation)
```

`LoadFile4` returns `errs=1` (swGenericError) or throws `0x800706BE`, the
process dies, and a **10 mm cube** STEP reproduces it -- so the file is
irrelevant. Four hypotheses were tested and eliminated by measurement before
the real one: launch method, `swMultiCAD_Enable3DInterconnect` left `True` by
the other agent's crashed run, a cold main frame (creating and closing a
document first does not help), and stale `%TEMP%\swx*` directories. What
actually correlated was a second client: when the staging tree went quiet for
two minutes every call worked, first time, repeatedly.

**A build should take a lock before touching SolidWorks.** There is no
API-level protection, the failure is a crash rather than an error, and it takes
the other client's unsaved work with it. `Marshal.GetActiveObject` also cannot
choose between two running instances, so "just start your own" is not an
answer.

### SolidWorks CAN be started by a script -- `CreateObject` is the only bad way

§1 says "start SolidWorks by hand", which is right about `CreateObject` and
wrong as a general rule. Launching **the executable as a process** registers in
the ROT normally:

```bash
nohup powershell.exe -NoProfile -Command \
  "Start-Process -FilePath 'C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\SLDWORKS.exe' \
   -WorkingDirectory 'C:\Users\Ben'" >/dev/null 2>&1 &
```

`Marshal.GetActiveObject` then attached on the first try. Poll
`GetUserPreferenceStringValue(8)` until it returns a template path that exists
before issuing real work. `cmd.exe /c start ...` from WSL blocks the calling
shell; use `Start-Process`, backgrounded.

So the headless answer is: **a script can start it, attach to it, drive it and
leave it**. What it cannot do is share it.

### End to end, timed

| stage | s |
|---|---|
| attach + readiness gate | 2.0 |
| `LoadFile4` the three-body STEP, verify 3 solids against build123d | 2.8 |
| `InsertCombineFeature` ADD + verify one solid | 0.2 |
| `SaveAs` the combined SLDPRT | 0.3 |
| classify 12 faces against 3 oracle bodies | 8.8 |
| select both junction edge sets + cross-check | 0.03 |
| two fillets (variable radius 3.0 mm, face 2.0 mm) + verification | 1.4 |
| binary STL export + SaveAs | 0.2 |
| **total, single scripted invocation** | **15.5** |

Face classification is 8.8 s on the 12-face spline-pod body and 9.6 s on the
144-face polyline one -- near-identical, because the cost is loading the three
oracle STEPs, not the face loop. Cache those and the whole run is under 8 s.
The full 32-trial matrix (4 methods x 2 junctions x 4 radii, each on a freshly
re-opened part) takes 83 s on the spline pod and 186 s on the polyline one.

### The STL is fit for snappyHexMesh

| | SolidWorks | build123d, same body unfilleted |
|---|---|---|
| format | binary | binary |
| triangles | 32 498 | 36 994 |
| **watertight** (every edge paired, opposite senses) | **yes** | yes |
| enclosed volume | 229 929.140 mm3 | 228 702.785 mm3 |
| against its own B-rep | **+0.041%** | -0.551% |
| bounding box agreement | 0.02 mm | -- |

Units are mm with `swExportStlUnits = 0`; set `swSTLQuality_Custom` with
`swSTLDeviation` 2e-5 m and `swSTLAngleTolerance` 5 deg, and
`swSTLDontTranslateToPositive = true` or the part is moved into the positive
octant. Restore all seven preferences in a `finally` -- they are the user's.

Worth noting that SolidWorks' tessellation sits **outside** its own B-rep
(+0.041%) where OCC's sits inside (-0.551%) at a comparable triangle count.
For a drag number that is a 0.6% wetted-area difference between the two
meshers on identical geometry, which is larger than several of the design
deltas being chased.

### Verdict for the CFD pipeline

- **Yes, SolidWorks can be a scripted stage.** 15.5 s, one invocation, no UI.
- **It must own the SolidWorks process** -- take a lock, or it crashes.
- **1-3 mm fillets are reachable on the body junction today** (variable radius),
  and on the pod junction only after the pod is revolved from a spline.
- The face-fillet path is unverified and sometimes ignores its second face set;
  do not build on it without checking where the blend landed.

## 8.11 Reviewing the MERGED aero envelope, and what actually blocks a blend (2026-09-12)

Inputs: `params.yaml` sha256 `6f2d2a38…`, `frame/model.py` `dc04454e…`, snapshot
in `design/out/swreview6/snap/`. Generators: `design/out/swreview6/`
(`build_parts.py`, `probe.py`, `probe2.py`, `swreview6.cs`, `run_sw.py`).

This is the first review of a `cfd_surface` that is already ONE fused solid
(`fairing.aero_overlap: 2.0`, `fairing.section_curve: spline`,
`nacelle.profile_curve: spline`), so there is nothing left to Combine. The
question changes from "can SolidWorks fuse this" to "is the fused thing
clean", and the answer has a shape nobody had measured before.

### The junction is NOT a loop — the bare CF tube breaks it open

Face ownership (docs 8.10's classifier, extended to four constituent types:
fuselage / fairing / nacelle / tube) partitions all 58 faces of the merged
body with **0 ambiguous and 0 unowned**. The junction edge sets then come out
as, SolidWorks and build123d agreeing edge-for-edge:

| junction | edges | arc mm | connected components | closed? |
|---|---|---|---|---|
| fairing\|fuselage | 28 | 281.031 | 8: 4×{3e,4e} | **open**, 16 free ends |
| fairing\|nacelle | 24 | 251.307 | 8: 4×{5e,1e} | **open**, 16 free ends |
| fairing\|tube | 16 | 89.465 | 16 single edges | open |
| fuselage\|tube | 8 | 73.978 | 8 single edges | open |
| nacelle\|tube | 8 | 16.745 | 8 single edges | open |

**Not one junction ring closes.** The arm tube is exposed between the
fuselage and the fairing root (two patches per station, ~6.7 mm² each) and
again between the fairing and the pod — and there the exposed strip is
**2.222 mm long by 0.0182 mm wide, 0.04034 mm² of face area**, bounded by
exactly two edges, one `fairing|tube` and one `nacelle|tube`. Eight of those
hairlines exist, two per station.

That hairline is not a hole: the body is one solid, `Check2() == 0`, and the
unfused neighbours measure **0.000000 mm** apart (they overlap by 70.6 mm³ at
the body and 273.1 mm³ at the pod). It is a sliver of the tube's own surface
surviving between two intersection curves that do not quite meet.

### That sliver, not the radius, is what caps the fillet

The matrix below is 96 + 32 trials, each on a freshly re-opened copy of the
unfilleted part.

| edge set | scope | 0.5 | 1.0 | 2.0 | 3.0 mm |
|---|---|---|---|---|---|
| fairing\|nacelle (6e, incl. the orphan) | one station | ok | fail | fail | fail |
| fairing\|nacelle (5e chain, orphan dropped) | one station | **+18.33** | **+53.10** | **+128.69** | fail |
| fairing\|fuselage (7e) | one station | ok | fail | fail | fail |
| fairing\|fuselage (4e chain) | one station | **+14.72** | fail | fail | fail |
| either junction | **all four stations at once** | fail | fail | fail | fail |

Dropping the ONE orphaned edge that the hairline cuts off takes the pod
junction from 0.5 mm to **2.0 mm** — a 4× radius for deleting one 6.5 mm edge
from the selection. The body junction is genuinely radius-limited at 0.5 mm
and closing its ring with the tube's own edges (11 edges, 0 free ends) does
not help: still 0.5 only. So "open chain" and "radius limit" are two
different blockers and this envelope has one of each.

### Fillet per CONNECTED COMPONENT, one feature each — then both junctions blend

Splitting each junction into its connected components (union-find over
`IEdge.IGetStartVertex()` / `IGetEndVertex()` points) and giving every
component its own `FeatureFillet3` puts **eight fillet features on one body**:
four pod junctions at R=2.0 and four body junctions at R=0.5, one solid
throughout, `Check2() == 0` after every one.

```
faces 58 -> 88;  36 new blend faces, 937.592 mm2
volume 314491.975 -> 315086.126 mm3  (+594.151, +0.1889%)
```

**This settles the question 8.10 left open.** "Only one junction can be
filleted per body" was neither a geometric limit nor a feature-manager
artefact: it was the **edge set**. Hand `FeatureFillet3` a set that spans
several disjoint junctions and it refuses, silently, at every radius — 28
edges over 4 stations fails where the same 4 edges of one station succeed.
Split by component and the features coexist happily.

### Constant radius beats variable radius here — the reverse of 8.10

On the single-station test article of 8.10, `swFeatureFilletType_VariableRadius`
with equal poles succeeded where constant radius failed. On this envelope
**variable radius never succeeded once**, in 64 trials, at any radius, on any
junction or scope — including the closed 11-edge ring. Constant radius is what
works. Both results are reproducible; the rule is therefore *try both*, not
*prefer variable*. Constant radius also stays non-monotonic (0.5 ok, 1.0 fail,
2.0 ok on the closed pod ring), which is the same signature as 8.10.

### Six instruments were wrong before the geometry was

**1. `Face.center()` is not a point on the face** — build123d side. Classifying
envelope faces by the ownership of their centroid produced "2 unowned faces"
and "4 faces on three different solids at once", both nonsense: the centroid of
a curved face is off the surface. SolidWorks' classifier pulls its sample back
with `GetClosestPointOn` and reports 0 ambiguous, 0 unowned. Same algorithm,
opposite verdict, and the one that did the pull-back is right.

**2. The edge-ownership tolerance is not one number.** At 1e-6 the b3d
classifier called `fuselage|tube` **6 edges**, an impossibility on a 4-fold
symmetric airframe. A sweep over 1e-7…1e-3 shows the fairing sets are
completely tolerance-independent (28 / 24 / 16 from 1e-6 to 1e-3) while
`fuselage|tube` only resolves at **≥1e-5**, where it becomes 8 — 2 per station
— and then matches SolidWorks to +0.0022%. Sweep the tolerance and demand the
symmetry the part has; do not pick 1e-6 because the last part needed it.

**3. `ICurve::GetLength3(t0, t1)` is the right ruler; the 64-chord polyline is
only a good one.** 8.10 caught `GetCurveParams2()[6..7]` over-reading conics by
63%. Here the two agree to 0.05% everywhere, because none of these edges is a
periodic conic. `GetLength3` over the same parameter range is one call instead
of 65 and is what the numbers above use.

**4. `IMeasure` cannot be used headless.** `doc.Extension.CreateMeasure()` then
`Calculate(null)` returned false on every edge set tried, so the third,
UI-equivalent ruler produced `NaN` throughout. Not a fallback; drop it.

**5. The 8.9 slope instrument does not exist on a spline revolve.** A polyline
revolve is one conical face per profile segment, so `ConeParams[7]` per face,
sorted up the axis, reads the profile's slope directly — that is how the
26.29° graft and the 1.1005° continuous profile were measured. With
`nacelle.profile_curve: spline` the pod is **0 conical faces and 1 surface of
revolution**, and that instrument reads nothing at all. Replacement: sample one
meridian with `ISurface.Evaluate(u, v, 0, 0)` over `IFace2.GetUVBounds()`,
convert to (axial station, radius) about the pod axis, and look at the largest
step in the slope sequence **as a function of sample count**:

| N | max \|Δslope\| |
|---|---|
| 100 | 0.9102° |
| 200 | 0.4552° |
| 400 | 0.2276° |
| 800 | 0.1138° |

Exactly 2.00× per doubling. A graft does not shrink under refinement; pure
discretisation halves. The refinement ladder *is* the test — a single number
at one N would have been meaningless.

**6. `OpenDoc6` on a path you already hold open, then `QuitDoc`, destroys your
own reference.** The fillet matrix opens the envelope per trial and quits it
after. The review had the same file open as `envDoc`; `OpenDoc6` returned THAT
document (8.9, symptom 5), the trial's `QuitDoc` closed it, and the next call
on `envDoc` threw `RPC_E_DISCONNECTED (0x80010108)` from `GetTitle()` — after
the matrix had finished and printed, so the data survived but the run was
scored a failure. Release the document before any loop that opens the same
path.

One more, on the build123d side and cheap to repeat: **`Solid.vertices()` is
not the silhouette.** Using it to measure a revolved pod's extent along an axis
gave [−8.132, −0.318] mm for a body that spans ±11.5 — a revolve has vertices
only on its seam. Use `bounding_box()` or a projection, never the vertex list,
on anything curved.

### The two kernels disagree ONLY at the sliver

Junction arc length, per connected component, SolidWorks vs build123d:

| component | b3d | SolidWorks | Δ |
|---|---|---|---|
| fairing\|fuselage, all 8 chains | 281.031 | 281.031 | **0.0000%** |
| fuselage\|tube, 8 edges | 73.977 | 73.978 | +0.0022% |
| fairing\|tube, 16 edges | 89.465 | 89.465 | 0.0000% |
| fairing\|nacelle, the four 5-edge chains | 56.143 ×4 | 56.143 ×2, 56.440 ×2 | 0 / +0.53% |
| fairing\|nacelle, the four orphan edges | 7.994 ×4 | 6.435 ×2, 6.636 ×2 | **−17 to −20%** |
| nacelle\|tube, the 8 sliver edges | 2.2224 ×8 | 2.059 ×4, 2.128 ×4 | **−4 to −7%** |

Everything away from the hairline agrees to 0.002% or better. Everything that
touches it disagrees by up to 20% of a short edge, and SolidWorks' re-knit is
not even 4-fold symmetric there (56.143 on one diagonal, 56.440 on the other)
while build123d's is. Two kernels differing on a feature 18 µm wide is the
expected outcome; the useful reading is that **the disagreement is a map of
where the model is ill-conditioned**, and it points at one feature.

### STEP round-trip, as usual, is not free

| part | b3d mm³ | SolidWorks | Δ | faces |
|---|---|---|---|---|
| core_body / arm_tube / shim | — | — | **0.00000%** | equal |
| cowl_fwd | 15396.380 | 15380.891 | −0.10060% | 13 → **15** |
| cowl_aft | 13369.413 | 13356.951 | −0.09321% | 12 → **14** |
| nacelle_mount | 9698.777 | 9699.446 | +0.00690% | 15 = 15 |
| arm_fairing | 8622.094 | 8623.527 | +0.01662% | 6 = 6 |
| **aero_envelope** | 314658.706 | 314491.975 | **−0.05299%** | 57 → **58**, 150 → 153 edges |

Planar/cylindrical parts survive exactly; spline lofts lose ~0.1% and gain
faces. The envelope's extra face is a fuselage face SolidWorks splits on
import. None of this is an error in either model — it is the budget, and it is
larger than several of the design deltas being chased, so a drag number must
state which B-rep it came from.

### Timing

| stage | s |
|---|---|
| attach + readiness gate | 1.5 |
| import 8 STEPs, verify each against build123d, SaveAs | 17.6 |
| load the 4-type oracle (13 bodies) | 7.2 |
| classify 58 faces | 9.7 |
| 6 junction edge sets + components + 2 rulers | 10.9 |
| the pod: extents, tip flat, meridian ladder | 5 |
| 8 fillet features (4 × R2.0 + 4 × R0.5) + verification | 110 |
| **total, one scripted invocation** | **174** |

The 96-trial fillet matrix is a further ~280 s, and the proximity cross-check
of the edge selection (which agreed exactly, 28 / 24 / 16 / 8) is 135 s on its
own — worth running once per geometry change, not every run.

## 9. Starting a fresh project (e.g. the robot chassis)

### Do this differently

1. **Start in C#. Skip VBScript entirely.** The `csc.exe` setup is about two
   minutes; the VBScript dead ends in §5 cost the best part of a day. The only
   reason `swmacro.py` is still VBScript is that it was already working.
2. **Keep the two-language split.** Python owns the geometry and writes a
   manifest; C# owns SolidWorks and reads it. Neither side has to know the
   other's hard parts, and the manifest is a readable artefact you can diff.
3. **Write the verification before the feature.** Volume and centre of mass,
   compared against something computed *outside* SolidWorks. Several of these
   APIs return success and do nothing (§5), so a build that is not measured is
   not a build that worked.
4. **Do not reconstruct feature trees unless editability is the goal.** STEP
   import plus explicit transforms produced a correct 16-component assembly far
   faster than rebuilding geometry natively. Rebuild natively only for the one
   part you actually intend to edit in SolidWorks.

### Is `swtool.cs` reusable as-is?

**Roughly 70%.** Take these unchanged:

- `Connect()` with the busy-retry loop
- the import → verify → `SaveAs` loop, including the `doc.GetType()` check
- the manifest parser and the `Check()` / failure-count pattern
- the whole verification block — transforms × part centre of mass, summed and
  compared against the assembled solid *and* an external reference

Four things want generalising before a chassis:

1. **`comp <name> <rotZdeg>` is Z-rotation-only** — and in the end fpv250 does
   not even use it, because exploding the assembly makes every component an
   identity placement (§7). A chassis built from vendor parts *will* need real
   placement. Widen it to `comp <name> rx ry rz tx ty tz` (degrees, mm) and
   build the matrix from that; the `RotZ()` helper is already the right shape,
   it just needs two more axes and a translation. Bear in mind a component
   transform is a rigid motion — determinant +1 — so a mirrored instance is a
   separate part file no matter how general the manifest gets.
2. **It assumes one solid per STEP and one part per file.** True for parts out
   of a parametric model, false for vendor downloads — a motor or a bearing
   arrives multi-body or as a real assembly. Fold the §4.8 flattening into the
   C# side, and decide explicitly whether a multi-body STEP becomes one
   multi-body part or several.
3. **No custom properties.** A chassis has a BOM; `swCustomPropertyManager`
   stamping part number, material and vendor at import time is cheap then and
   tedious later.
4. **It only ever builds from scratch.** For a design you iterate on, add an
   "open the existing assembly and update component transforms" path so
   downstream work — drawings, mates you did add, appearances — survives a
   re-export.

What does **not** need adding: mates. If the parts carry their own position,
an explicit `Transform2` is simpler, exact, and cannot conflict (§7).

## 10. Files

| file | what it is |
|---|---|
| `design/swexport.py` | writes section profiles as `.sldcrv` / `.dxf` |
| `design/swmacro.py` | generates `build_profiles.vbs` — 3D sketches + scripted loft |
| `design/swassembly.py` | explodes `assembly.step`, writes the manifest, compiles and runs `swtool.exe` |
| `design/swtool.cs` | the C# SolidWorks driver: STEP import, assembly, verification |
| `design/swverify.cs` | part-level checks: nose openings, the camera bore, the nacelle tip, fairing orientation (§8) |
| `design/out/swreview/build_variants.py` | builds a parameter study's CASES from a frozen `frame/` snapshot, exports STEP, measures in build123d (§8.8) |
| `design/out/swreview/swreview.cs` | imports each variant, cross-checks volume/solids against build123d, runs the silhouette scan (§8.8) |
| `design/out/swfillet/build_parts.py` | overlapping fairing/body/nacelle solids + the three-product STEP and junction manifest (§8.10) |
| `design/out/swfillet/occ_control.py` | the OCC fillet control the SolidWorks numbers are measured against (§8.10) |
| `design/out/swfillet/swfillet.cs` | import, Combine, face-ownership edge selection, the fillet matrix, STL (§8.10) |
| `design/out/swfillet/stlcheck.py` | STL triangle count, enclosed volume, watertightness by edge pairing (§8.10) |
| `design/out/swcad5/build_parts.py` | exports the PRINTED parts (`M.build`) and the AERO ENVELOPE (`M.cfd_surface`) as single-product STEPs (§8.9) |
| `design/out/swcad5/verify_b3d.py` | the build123d half of the cross-check: pocket, bolt holes, nose profile, cowl openings (§8.9) |
| `design/out/swcad5/swcad5.cs` | imports both sets, measures the pocket / bolt holes / nose cone / flare mouth in SolidWorks (§8.9) |
| `design/out/swcad5/run_asm.py` | retry wrapper round `swassembly.py` for when SLDWORKS.exe is being shared and keeps dying (§8.9) |
| `design/out/swreview6/build_parts.py` | the adopted printed parts + the fused `cfd_surface`, the 4-type ownership oracle, junction classification (§8.11) |
| `design/out/swreview6/probe.py` | the tolerance sweep that showed the edge classifier needs 1e-5, not 1e-6 (§8.11) |
| `design/out/swreview6/probe2.py` | junction topology in build123d: components, free ends, and the 0.0182 mm tube sliver (§8.11) |
| `design/out/swreview6/swreview6.cs` | import + cross-check, face ownership, junction edges, the pod meridian ladder, the fillet matrix and the per-component blend (§8.11) |
| `design/out/swreview6/run_sw.py` | manifest + compile + run wrapper for the above (§8.11) |
| `.claude/skills/solidworks/SKILL.md` | the operational short version of this document |

Both Python tools stage everything they touch under `C:\Users\<you>\fpv250-sw\`
(`steps/`, `parts/`, `cs/`) — a scratch area, not the repo. The repo keeps only
the generators.

---

## 11. The project setup pass — mm, real materials, and which way is up (2026-09-26)

Everything above gets geometry *into* SOLIDWORKS. This is what makes it a
project you can work in. Three commands, after `swassembly.py` has run:

```
cd design
.venv/bin/python swmaterials.py                 # params.yaml -> fpv250.sldmat
.venv/bin/python swproject.py                   # units + materials + provenance
.venv/bin/python swexport.py --sections 25      # the NATIVE loft: profiles
.venv/bin/python swmacro.py                     # -> build_profiles.vbs
cmd.exe /c "cscript //nologo C:\Users\Ben\fpv250-sw\build_profiles.vbs"
```

### Units and materials

Before this existed, every component sat at SOLIDWORKS' default **1000 kg/m³**,
so the assembly's "mass" was its volume in cm³ and the 250 g budget could not
be read off the model at all. `swproject.py` sets MMGS (mm, degrees, **mass
properties in grams and mm**) and assigns a real material to every part.

**The library is GENERATED from `params.yaml`** (`swmaterials.py`), because a
hand-typed material table is a second copy that drifts — the same argument this
project makes about `diff all` and sliced mass. It registers itself by adding
its folder to `swFileLocationsMaterialDatabases`, so it also shows up in the
Material dialog for hand use.

**Three API facts, all reflected rather than guessed:**

| want | it is | not |
|---|---|---|
| material DB folders | `swUserPreferenceStringValue_e.swFileLocationsMaterialDatabases` = **28**, a `;`-delimited STRING | `swUserPreferenceStringListValue_e` — which has three members and none is this |
| density | `swUserPreferenceDoubleValue_e.swMaterialPropertyDensity` = 7 | — |
| save from VBScript | `SaveAs2(path, 0, True, False)` — returns a code, **no `[in,out]`** | `Save3` / `SaveAs3` / `SaveAs4`, all byref → *Type mismatch* |

`GetMaterialPropertyName2` also has a byref out-param, so **reading** a
material back needs C# too. That is the whole of rule 1 again.

**Density provenance rides on the part**, as custom properties
(`Material` / `DensityBasis` / `Source`), because a number with no provenance is
exactly how a stale sliced mass passes for a measured one:

- **LW-ASA 352 kg/m³ is [M] as-printed** (mass / CAD volume, eleven coupons) →
  those masses are TRUE.
- **PA6-CF20 1170 kg/m³ is TDS SOLID** → an UPPER BOUND; a printed part is
  ~0.85 of it. Re-run `slicemass.py` and switch. The part says so.
- SOLIDWORKS materials are isotropic, so `sigma_z`, the wet column and Tg
  cannot live in the material — they ride as custom properties and the
  material carries the optimistic **dry XY** numbers.

Frame as set up: **105.24 g** (printed parts + tubes + shim, no electronics).

### Which way is up

`Rot(Z=-90)`, i.e. **(x, y, z) → (y, −x, z)** — rule 17's display frame, now
applied by `swassembly.py` (`to_display`) and `swexport.py` by DEFAULT, with
`--body-frame` to opt out. The body frame is +Z nose, −X top; SOLIDWORKS draws
+Y up and lights and shadows from there, so imported raw the aircraft lies on
its side and the shadow falls off its flank. After the rotation the top is at
+Y, the belly (+X, where the camera looks) is at −Y, and the floor shadow lands
under the aircraft.

It is a rotation **about Z**, so every loft section stays planar at the same z
and the loft's structure is untouched — verified: volume 200.688 cm³ before and
after, and the assembly's independent reference CG moved
(−0.126, 0.000, −0.132) → (0.000, +0.126, −0.132), exactly as the transform
predicts. **Only the SOLIDWORKS copies turn.** `design/out/` STEPs and the CFD
STLs stay in body coordinates, because `cfd.py`'s flow-frame rotation is
defined on them.

### The native, editable fuselage

`build_profiles.vbs` builds **25 `3DProfileFeature` sketches and one `Blend`** —
a real feature tree you can drag, re-sketch and re-loft, saved as
`parts/fuselage_native.SLDPRT`. It is the editable master, not an assembly
component.

**Fidelity has moved and the staging README is stale.** It records −0.10 % on a
2026-09-12 body. Measured 2026-09-26 on the current one:

| | volume |
|---|---:|
| model (25 sections, spline) | 201.275 cm³ |
| `--fidelity` prediction (linear loft) | 200.157 cm³ (−0.56 %) |
| **SOLIDWORKS `Blend`, measured** | **200.688 cm³ (−0.29 %)** |

So SOLIDWORKS' loft is better than a ruled surface but not the model's spline.
**Still do not set start/end tangency** — a spline blend overshoots between
profiles and gets worse.

### Where the hand-editing line is (Ben, 2026-09-26)

> *"I can hand edit parts that are inside of the CFD."*

That is the rule, and it is a good one: **the wetted surface stays parametric
and CFD-validated; anything the solver never sees is free to edit in
SOLIDWORKS.** Internal bores, pockets, bosses, sockets and ribs are inside the
envelope and change no drag number. The moment an edit moves the OUTER surface
it is a new shape and `docs/handoff.md` rule 2 applies — back out as STL, run
against the parametric shape as control, and record in `params.yaml` which
features SOLIDWORKS owns.

---

## 12. The native part set — `design/swnative.py` (2026-09-26)

Four generators, one per part family, each emitting a `.vbs` that builds a REAL
feature tree and then **measures itself against the parametric model**:

```
cd design
.venv/bin/python swnative.py fuselage --half 0   # shell + cut the nose half
.venv/bin/python swnative.py fuselage --half 1   # ... and the tail half
.venv/bin/python swnative.py pod
.venv/bin/python swnative.py fairing
.venv/bin/python swnative.py core
cmd.exe /c "cscript //nologo C:\Users\Ben\fpv250-sw\build_<part>.vbs"
```

| part | native | model | delta | tree |
|---|---:|---:|---:|---|
| `fuselage_native` | 200,687.6 | 201,275 | **−0.29 %** | 25 sketches + Blend |
| `fuselage_shell` | 28,373.1 | — | — | + Shell |
| `cowl_fwd_native` | 15,134.0 | 15,474.9 | −2.2 % | + Cut |
| `cowl_aft_native` | 13,151.1 | 13,462.3 | −2.3 % | + Cut |
| `pod_native` | 17,015.7 | 17,016.3 | **−0.004 %** | sketch + Revolve |
| `fairing_native` | 12,614.1 | 12,629.9 | **−0.12 %** | 21 sketches + Loft |
| `core_native` | 24,824.6 | 24,718.2 | **+0.43 %** | 3 extrudes + hole cut |

**The revolve is essentially exact and the lofts are not**, which is the useful
pattern: a revolve of the same meridian is the same operation in both kernels,
while a loft is each kernel's own blend between the same sections. The cowls'
−2.2 % is a different thing again — SOLIDWORKS' Shell is a TRUE NORMAL OFFSET
and the model's cavity is a PARALLEL LOFT (`_fuselage_solid(shrink=wall)`), and
they diverge where the body tapers. Use the native part to work in; use the
parametric one for any number that matters.

Two deliberate omissions, both INTERNAL and therefore hand-edit work under
Ben's rule: the core's four arm-tube bores (each needs its own 45° reference
plane) and the pod's internals (motor pocket, bolt bores, rod bore). The core
delta above is against the model **without** its bores; the bores remove a
further 3,984.9 mm³.

### Six API facts this cost, none of them guessable

1. **`FeatureCut4(Sd, Flip, Dir, …)`: `Flip` is "FLIP SIDE TO CUT", not the
   direction.** Using it to take the other half of a body cuts everything
   *outside* the profile — and with a rectangle that already encloses the body
   that is nothing, so the feature returns **Nothing** every time. Direction is
   `Dir`, the third argument. This cost four failed runs and a wrong theory
   about state leaking between passes.
2. **`FeatureExtrusion3` with `Sd = False` and a zero second distance returns
   Nothing.** A two-ended extrude with one end of zero length is not a feature.
   Pass `Sd = True` when you only want one direction.
3. **`GetBodies2` needs its arguments cast.** `GetBodies2(0, True)` returns
   something that is not an array and `IsArray` says so — so a `BodyCount`
   helper written that way silently reports **0 bodies**. It must be
   `GetBodies2(CLng(0), CBool(True))`. The verification helper had the bug it
   existed to catch.
4. **`IModelDoc2::GetPartBox` raises *Type mismatch* from VBScript**, cast or
   not, and `GetBodies2`'s elements will not bind to a `Body2` with `Set`
   either. There is no VBScript route to a bounding box here; use C# or design
   the need away.
5. **`swEndCondThroughAllBoth` is 9, not 8** — 8 is missing from the enum.
6. **`SaveAs2(path, 0, True, False)` works from VBScript** (returns a code, no
   `[in,out]`), where `Save3` / `SaveAs3` / `SaveAs4` all raise Type mismatch.
   It returns **0 for success**, so `If ok Then` reads a good save as a failure.

### The pod, split three ways (`swnative.py podsplit`, 2026-09-26)

Split at the mount face, which already exists in the model — `mount_z` −4.0 and
`mount_face_thk` 7.0 — so the planes are not invented:

| piece | local Y | volume | vs integrated meridian | what it is |
|---|---|---:|---:|---|
| `pod_cone_native` | 0.00 … 25.40 | 6,476.3 | +0.04 % | the nose. **The ASA candidate — 13.67 g over four pods.** No load, away from the can |
| `pod_mount_native` | 25.40 … 32.40 | 3,235.3 | +0.06 % | the 7 mm slab every motor bolt lands in. Prints FLAT |
| `pod_cowl_native` | 32.40 … 48.40 | 7,304.6 | +0.05 % | the shroud. Bonded on after; CFD says it stays full |

They tile exactly — no gaps, no overlaps, one body each, summing to 17,016.2
against the whole pod's 17,015.7.

**Each piece is its OWN REVOLVE, not a cut off the whole pod, and that was not
the first plan.** Cutting a solid at a known station from VBScript is a swamp:

- `FeatureCut4` with `T0 = swStartOffset (3)` + `ThroughAll` returns **Nothing
  in all four** flip/direction combinations, on a body whose bounding box was
  independently measured to contain the plane.
- Defining the band with the *profile* instead (rectangle on the Front plane,
  `ThroughAllBoth`) either **removes nothing** (`Flip` False) or **fails**
  (`Flip` True).

Re-deriving each piece from a clipped meridian sidesteps all of it, reuses the
revolve path that is already exact here, and gives each part its own editable
profile sketch — which is better for hand-editing anyway.

**Two process notes, both learned the hard way in this session.** First, a
bounding box is worth compiling for: `cs/swbox.cs` is 30 lines of C# and it
ended three rounds of guessing about which way a part was oriented — VBScript
cannot read one at all (`GetPartBox` raises Type mismatch, and `GetBodies2`
elements will not bind with `Set`). Second, **the pod's sketch plane was moved
from Right to Front on purpose**: on the Right plane the solid came out correct
(volume matched the model to 0.004 %) but a cut at a known station sliced it
somewhere else and the two pieces did not sum to the whole. Sketch on the plane
whose axis mapping you can state, not the one that looks natural.

**And do not trust an isometric render of a squat solid of revolution.** All
three pieces render as "a disc with a fin", which reads as a failed revolve and
is not — the fin is the shadowed side. The bounding box settled it in seconds.

### Sketch plane → global axis mapping, measured (2026-09-26)

Guessing this is what sent the first pod split into the weeds. A 2×2 mm post
placed at sketch (10, 4) on each standard plane, then measured with
`cs/swbox.exe`:

| plane | sketch x → | sketch y → | + extrude → |
|---|---|---|---|
| Front (XY) | +X | +Y | +Z |
| **Right (YZ)** | **−Z** | **+Y** | **+X** |
| **Top (XZ)** | **+X** | **−Z** | **+Y** |

Only Front is the obvious one. Sketch on the plane whose mapping you can state,
or measure it — the experiment above takes one run and settles it for good.

### The clocking spigot (`swnative.py stub`, 2026-09-26)

`stub_native`: the aerofoil section over r 46.00 … 52.81, rod bore Ø8.7, and a
**Ø4.0 × 3.0 peg 8.5 mm aft of the tube axis**, with a Ø4.2 × 3.2 socket in
`fairing_native`'s outboard face. Loft 2,028.8 → bore 1,623.9 → **1,661.6 mm³**;
the peg adds exactly 37.7 mm³ (π·2²·3) and the socket removes 44.4 against
π·2.1²·3.2 = 44.3.

Off the chord axis **on purpose**: the section is symmetric, so a concentric
feature cannot stop the fairing going on 180° out. The peg keys LE to TE.

This replaced the sleeve Ben originally asked for, which does not fit: thin41
leaves **0.30 mm of wall at r 46 falling to 0.06 at the tip** against 0.84
printable, and the rod cannot go deeper to move the bond into the pod either —
`rod_end_offset −7.0` is `4.243 + 2.3 + 0.45`, and the bore already grazes the
two inboard driver bores (0.043 mm³ each).

### ⚠️ OPEN: FeatureCut4 will not cut the revolve-built pod parts

The pod internals (rod bore, driver bores, head seats, shanks, motor pocket)
are **not built**. `FeatureCut4` returns `Nothing` on `pod_cone_native` and its
siblings, and this is what has been ruled out:

- not the plane — Front, Right and Top all fail identically;
- not the end condition — ThroughAll, ThroughAllBoth and Blind all fail;
- not the direction — both `Dir` values fail;
- not feature scope — all four `UseFeatScope`/`UseAutoSelect` combinations fail;
- not the argument count — 27 args, checked against the reflected signature,
  and the **identical call succeeds** on `cowl_fwd_native`, `core_native` and
  `stub_native`;
- not the sketch — it is created (confirmed by name, `Sketch2`) and re-selects
  `True`;
- not part health — `EditRebuild3` returns True, 19 features, **0 in error**,
  and the document is not read-only.

**RESOLVED to a reproducible case (2026-09-26). It is the REVOLVE, and it is
not the round trip.** Cutting the internals in the same script that creates the
revolve fails identically — rod bore, driver bores, shanks, head seats and the
motor pocket, all `False`, on parts seconds old. Reduced to a minimal case:

```vbscript
' A Ø20 x 20 cylinder, revolved from a 4-line rectangle + centreline
' on the Front plane. Volume reads 6283.2 mm3 = pi*10^2*20, exactly.
' Then a Ø6 circle on the Front plane, FeatureCut4 ThroughAll:
'   -> returns Nothing, volume 6283.2 -> 6283.2
```

> **SUPERSEDED 2026-09-27 for the engine path.** `part.build_printed_pod` v1 cut
> the revolved pod SEVEN times with `FeatureCut4` (boss bore, three bolt stages, pocket,
> rod bore, split): every cut removed material, and the part matched the model to
> +0.011 %. The engine's revolve is `FeatureRevolve2(true, true, false, false, false,
> false, Blind, 0, 2π, …, true, true, true)` on a sketch drawn in model coordinates
> with AddToDB scoped, and each cut sketch sits on a 3-point plane
> (`SwLoftedPart.CutCircles`). The minimal case below was the legacy VBScript
> path; which of those differences matters was never isolated.

**`FeatureCut*` will not cut a body made by `FeatureRevolve2`** in this
install. Also ruled out on that minimal case: all three standard planes; blind,
through-all and through-all-both; both `Dir` values; all four
`UseFeatScope`/`UseAutoSelect` combinations on the CUT; both feature-scope
settings on the REVOLVE; and **`FeatureCut2` (23 args) and `FeatureCut3` (26)
as well as `FeatureCut4`**. `FeatureCut5` does not exist. The sketch is real —
`CreateCircleByRadius` returns an object and the sketch re-selects `True` — the
part rebuilds with zero features in error, and it is not read-only.

**`FeatureExtrusion3` works fine on the same bodies and merges correctly**
(6,476.3 → 7,070.5 mm³ for an intersecting boss on the pod cone). So the kernel
is willing to boolean against a revolve; it is the cut entry point that is not.

**Two ways round, neither tried yet:**

1. **Tool bodies + Combine-Subtract.** Make each internal feature as a boss
   with `Merge = False` (proven to work), then `InsertCombineFeature(SWBODYCUT,
   mainBody, toolBodies)`. That needs C# — the tool-body argument is an array,
   which VBScript cannot build (rule 1) — but it keeps the revolve, and the
   revolve is the one construction here that matched the model **exactly**
   (−0.004 %).
2. **Rebuild the pod pieces as lofts through circular sections.** Lofts accept
   cuts (the stub's Ø8.7 bore went in without complaint). Costs the exactness:
   expect the fuselage loft's ~−0.3 % rather than −0.004 %.

Recommendation: (1). The pod is 46 % of aircraft drag and its shape is the one
thing in this model that is currently exact.

### The native assembly (`swasm.py` + `swasmnative.cs`, 2026-09-26)

`fpv250_native.SLDASM` — **28 components, 181,009.5 mm³, 189.411 g**, built from
the native parts rather than the imported solids.

| | |
|---|---|
| identity (already display-frame) | `core_native`, `cowl_fwd_native`, `cowl_aft_native`, `arm_tube_1..4`, `battery_native` |
| per station ×4 | `pod_cone/mount/cowl_native`, `fairing_native`, `stub_native` |

**This one has to derive its placements, and that is the dangerous part.**
`swassembly.py` never does: every solid comes out of `assembly.step` already in
aircraft coordinates, so it inserts at the identity and cannot be wrong. The
native parts are modelled in LOCAL frames — the pod stands on its own axis, the
fairing lies along its own arm — because that is how you want to open them to
edit. So each placement is computed, which is the situation that once put four
nacelles 11.8 mm out while every scalar check passed at +0.000 %.

The check is therefore one a symmetric-by-construction number cannot pass by
accident: **the assembly centroid must land on display-X = 0**, because
display-X is the body's lateral axis and the aircraft is mirror-symmetric about
it — but only if all four stations are right. It reads **+0.0001 mm**.

### ⚠️ The rotation matrix in `CreateTransform` is stored TRANSPOSED

The 16-double array is `[0..8]` rotation, `[9..11]` translation in **metres**,
`[12]` scale — and the rotation goes in **transposed** from the `v' = R·v + T`
matrix you are thinking of.

Written the obvious way, the four stations landed asymmetrically: assembly
centroid **X = −1.2704 mm** where symmetry demands 0, with total volume exactly
right (129,809.4 vs a predicted 129,809.3) and every component present. Volume
and component count cannot see a rotation error; only the symmetry check could.

**This had never been exercised.** `swtool.cs` has a `RotZ(deg)` helper that
looks row-major, but every imported component goes in at `RotZ(0)` — and an
identity matrix is its own transpose. The bug was latent in a helper that
"worked" for weeks.

### `battery_native`

A plain box envelope, 30.1 × 27.0 × 63.0 mm = **51,200.1 mm³ exactly**, in the
display frame so it places at `packing.battery_z` with an identity rotation. Its
material is a bulk stand-in — pack mass over pack envelope, **1582 kg/m³ → 81.0
g** — good for mass and CG and nothing else; the stiffness figures in it are
placeholders. It is the envelope the packing argument turns on: the usable bay
is 47.71 mm and this is 63.0 mm [M].

### The core's arm-tube bores, and turning a part to avoid an angled plane

`core_native` is now **20,774.3 mm³** against the model's 20,733.3 — **+0.20 %**,
tighter than the +0.43 % it had with the bores missing.

**Two bores, not four.** Opposite arms are collinear, so one bore through the
core serves both.

**The part is modelled 45° off the display frame on purpose.** The bores run
along the arms, which sit at 45° in the display frame, and cutting a horizontal
cylinder at 45° needs an angled reference plane — which means creating an axis
to hang the angle on, and `InsertRefPlane`'s constraint codes. Turn the PART
instead and the two bore lines land exactly on the X and Y axes, where the
standard Right and Top planes cut them with no reference geometry at all:

```
Right plane (normal X): sketch x -> -Z, y -> +Y  =>  (0,0) IS the X axis
Top   plane (normal Y): sketch x -> +X, y -> -Z  =>  (0,0) IS the Y axis
```

`swasm.py` puts the 45° back by placing the component with `Rz(-45)`.

**Why that needed its own check.** The assembly's symmetry test — centroid on
display-X = 0 — **cannot see a 90° error in this part**: the core's rails are
symmetric about that plane whichever way round they go. So the placement was
verified a different way, against a different kernel: export `core_native` to
STEP, apply the same `Rz(-45)` in build123d, and intersect it with each arm tube
at its station.

```
station FL/FR/RL/RR: tube vs placed core intersection = 0.000 mm3 each
```

Zero interference on all four, with a Ø7.785 tube in a Ø8.7 bore. **Pick a
check the error you are worried about could actually fail.**

## 2026-09-26 — three ways a scripted build lies about succeeding

All three cost a rebuild cycle on the native part set. None raised an error.

### `SaveBMP` returns `False` — the process is degraded, not the call

Six `SaveBMP` calls in a row returned `False` with no exception, no message and
an existing, writable output directory. Nothing was wrong with the script: the
**same script worked unchanged after restarting SOLIDWORKS**. `SLDWORKS.exe`
was at **1.16 GB**, which is inside the band where this project has already
seen it silently return `Nothing` from working calls.

So `SaveBMP → False` is not a bug to debug, it is a **symptom to measure**:

```
tasklist.exe /FI "IMAGENAME eq SLDWORKS.exe"
```

Over ~1 GB, restart first and re-test before changing a line. Note how cheap
the wrong path was here — the first instinct was a missing `shots\` directory,
and `mkdir -p` "fixed" nothing while appearing plausible.

Related: **`ActivateDoc3` is `Type mismatch` from VBScript** — it takes an
`[in, out] long*`, so it falls under rule 1 like `OpenDoc6` and `LoadFile4`.
Use `OpenDoc7`, or write it in C#.

### A `close()` between the build and the save throws the part away

The fuselage rebuild printed, in this order:

```
Loft: Loft1  solid bodies=1  volume=200.688 cm3
no active document
```

The loft worked. The driver script then ran `closeall.vbs` before
`savenative.vbs`, because "start each step clean" is a good habit everywhere
else in this file. Here it discards the freshly-lofted, never-saved part, and
`savenative.vbs` correctly reports that there is no active document. **The
close belongs before the build, never between a build and its save.**

### Patching a generated template with a blanket string-replace hits *every*
### template in the file

`swnative.py` holds eight VBScript templates in one module. Two separate
corruptions came from editing them by global replace:

1. Appending `feat` to a `Dim` line that already declared it produced
   `Dim secs, ..., vol, feat, feat` → *"Name redefined"*, a **compile** error,
   so the whole script died at line 40 having done nothing.
2. Adding guide curves to the **fairing** loft pasted the same block into the
   **stub** loft, which has no `guides` array → *"Variable is undefined:
   'guides'"* at run time, after the profiles were already drawn.

The stub is a two-section straight sleeve and guide curves are meaningless on
it, so the fix was to delete the block rather than generalise it. Both failures
were caught only because the builders **verify real geometry** (rule 12) rather
than trusting a return code — and both would have been caught earlier by a
`cscript //X`-style syntax pass over each generated `.vbs` before running it.

## 2026-09-26 — the native parts were faceted, and the model had already said why

Ben, on a render of the exploded pod: *"The pods have similar loft issues we
need to work through still."* He is right, and the cause is one line of the
VBScript path leaking into the geometry.

### The diagnosis: the shape is right, the TANGENCY is wrong

`swnative.py`'s `pod_vbs` revolves the meridian as **159 straight
`CreateLine` segments**. Measured against the true Bezier:

| | |
|---|---|
| max chord error | **0.001246 mm** |
| mean chord error | 0.000308 mm |
| normal break at each of 158 band edges | **0.339° mean, 0.926° max** |

So the pod is in the right *place* to about a micron, and is a stack of 158
conical facets. A revolved polyline is **C0**: every band edge is a crease.
That is the knurled / tree-ring texture on the render.

### The model solved this on 2026-09-12 and the SolidWorks path re-broke it

`frame/model.py::_pod_wire` is unambiguous, and it is worth quoting because it
prices the defect:

> *"The polyline revolve gives 79-81 conical faces. That is not cosmetic: it
> makes the fairing/pod junction a **112-EDGE shatter** averaging 0.7 mm, and
> neither OCC nor SolidWorks will blend across it. The identical profile as a
> spline revolve is the same pod to +0.001% volume, gives a **6-EDGE** junction
> over the same 78.47 mm, and then BOTH junctions fillet on one body
> simultaneously."*

`nacelle.profile_curve: spline` and `fuselage.section_curve: spline` were both
adopted that day. The native SolidWorks path then silently reintroduced the
polyline — on the one part whose shape is CFD-frozen — because
**`CreateSpline` needs a SafeArray of DOUBLE and VBScript cannot build one**
(rule 1). `swmacro.py` carried a docstring saying the polyline was *"not a
workaround forced on us"* because the model used polylines too; that had been
false since 2026-09-12 and is now corrected in place.

### The fix: C# can call `CreateSpline`, and it is worth it

`design/swspline.py` + `design/swpodspline.cs`. Verified: `CreateSpline` and
`CreateSpline2` both return a real segment from C# (`GetType()` = 3 = spline)
where VBScript gets `Nothing`.

| | polyline `pod_native` | spline `pod_spline_native` |
|---|---:|---:|
| **faces** | **162** | **3** |
| volume mm³ | 17015.7 | 17015.4 |
| centroid Y mm | 29.284 | 29.283 |
| bounding box | 24.38 × 48.40 × 24.38 | identical |

Same solid, 54× fewer faces. The straight **flats stay lines** — `pts[0]→pts[1]`
is the motor mount face and `pts[-2]→pts[-1]` the printable tip flat; splining
through them would round away features that exist for a reason.

**Two traps on the way, both silent:**

1. **`FeatureRevolve2` returns `null` if the axis selection failed.** Selecting
   the centreline as a `SKETCHSEGMENT` by position (mark 4) does not work here
   and leaves nothing selected; the revolve then returns null with no error.
   Select the **sketch by name** (`"Sketch1"`, `"SKETCH"`, mark 0) as the
   working VBScript pod does — the sketch carries its own centreline.
2. **The model and the assembly disagree on the pod's local origin, by a
   mirror.** `model.nacelle_meridian` runs **motor end → tip**; `swasm.py`
   places the pod with *"the TIP at Y = 0"* and `pod_vbs` built it that way.
   Same shape (verified: **0.0024 mm** max radius difference measured from the
   motor end), opposite origin. Caught only because the centroid moved 29.284 →
   19.117 while volume and bounding box were *identical* — the exact signature
   rule 14 warns about, and a reminder that volume+bbox cannot see a mirror.
   `swspline.py` reverses into the assembly's convention.

### One shared meridian, so the two representations cannot drift

`model.nacelle_meridian(p)` was extracted from `nacelle_mount` (unchanged —
`nacelle_mount(solid=True)` reads **17016.261627 mm³** before and after, i.e.
identical to 15 significant figures, the limit of double precision at that
magnitude). Both the model and `swspline.py` now call it. Two representations
are a check only while they share their **input** and differ in their
**kernel**; re-deriving the meridian in the SolidWorks path would have made
them two copies of one piece of arithmetic (skill rule 16).

### Still open

- **The fuselage has the same defect.** `section_curve: spline` in the model,
  25 polyline sections of 48 lines each in SolidWorks. Not yet converted.
- **`pod_native.SLDPRT` renders as a sliver** — a thin meridian face plus the
  motor disc — while its mass properties are correct (162 faces, 1 body,
  17015.7 mm³) and its shadow is a full pod. A display-state problem in that
  file, probably left by the `podsplit` tool-body work, not geometry.

## 2026-09-26 (later) — the fuselage too, and a shatter that is NOT the loft's

Ben: *"fix the fuselage the same way"*. Done — `design/swloft.py` +
`swfuseloft.cs`, the loft counterpart to `swspline.py`/`swpodspline.cs`. It
reads the SAME `sec*.sldcrv` files `swmacro.py` reads, so the two paths differ
only in the curve type.

Each section is a CLOSED spline, closed by **repeating the first point** at the
end — exactly what `_fuselage_solid` does (`ring.append(ring[0])` before
`Spline(*ring)`). Reproducing the model's construction is the whole point;
approximating it is what went wrong in the first place.

| | polyline `build_profiles.vbs` | spline `swfuseloft.exe` |
|---|---:|---:|
| **faces** | **50** | **3** |
| volume mm³ | 200 687.6 | **201 190.9** |
| error vs the model's 201 275.4 | **−0.292 %** | **−0.042 %** |
| bounding box | 36.61 × 39.73 × 200.00 | 36.63 × 39.76 × 200.01 |
| build time, 25 sections | 46–63 s (1200 `CreateLine` calls) | **6.9 s** |

So the spline loft is smoother, **7× more accurate**, and **8× faster**. The
accuracy is not a coincidence and it is worth understanding: a polyline
**inscribes** the true section — every chord cuts the corner — so the polyline
body is systematically UNDERSIZE, which is exactly the sign of the error.
The bounding box grows by the same mechanism.

Both spline builders are now the canonical writers: `swloft.py` writes
`fuselage_native` and `swspline.py` writes `pod_native` (pass
`--name *_spline_native` to rebuild the comparison pair). The cowl halves,
which are cut from the shell, inherited the smooth surface at **5 faces**
each. The full set rebuilt and `swasm.py` reports 28 components at centroid
X = **+0.0000 mm**.

### The pod split parts shatter, and it has nothing to do with this

Measuring after the change showed something alarming:

```
pod_native        3 faces        <- the fix
pod_cone_native   3203 faces     <- ?!
pod_mount_native   676 faces
pod_cowl_native    987 faces
```

The obvious reading is that trimming a spline surface splits it at every knot,
i.e. that the fix moved the problem downstream. **It did not.** Rebuilding the
whole chain from the POLYLINE pod gives:

```
pod_native        162 faces      (vs 3)
pod_cone_native   3203 faces     IDENTICAL
pod_mount_native   676 faces     IDENTICAL
pod_cowl_native    987 faces     IDENTICAL
```

Bit-identical downstream, from a source surface that differs 54-fold. So the
shatter is **independent of the pod's surface** — it lives in the
`podsplit` → `swcombine` path, it was there before any of this work, and it was
simply never measured. Worth writing down that the check that settled it was
cheap: rebuild the old way and count.

**This is a real open defect** — 3203 faces on a 4.9 cm³ cone is pathological,
and face shatter is precisely what `_pod_wire` says blocks blending:
*"neither OCC nor SolidWorks will blend across it."* Filed in `docs/TODO.md`.

## 2026-09-26 (later still) — the rest of the polyline paths, and one that had to stay

Ben: *"please continue resolving the polyline paths. the stub still has the
folding issue."* Both done. `design/swloftpart.cs` +
`design/swsplineparts.py` now build the fairing and the stub.

### Final state

| part | before | after | |
|---|---:|---:|---|
| `fuselage_native` | 50 | **3** | spline loft |
| `pod_native` | 162 | **3** | spline revolve |
| `fairing_native` | 89 | **9** | spline loft + guides |
| `stub_native` | 100 | **8** | spline loft + guides + density |
| `cowl_fwd/aft_native` | — | **5** | inherited from the shell |
| `core_native` | 96 | **96** | **deliberately unchanged — see below** |

### Why the stub folded when the fairing had already been fixed

Not the curve type, and not the dedup. The tip-chord taper is a smoothstep over
`tip_taper_len` (8 mm) ending at the nacelle's inboard reach:

```
ramp starts   r 44.81  ->  reach 52.81
stub spans    r 46.00  ->  52.81      ENTIRELY INSIDE THE RAMP
stub sampled  6 sections = 1.36 mm apart
```

The fairing only catches the ramp's first ~1 mm and got density plus guide
curves for it. **The stub is wholly inside the ramp and had neither** — it lofts
the steepest part of the taper at the coarsest spacing anywhere in the model.
It now gets 17 sections at 0.43 mm, five guide curves, and spline sections.
The crease at the trailing edge is gone.

**Guide landmarks are now COMPUTED, not hard-coded.** `swnative.py` carries
`guide_idx = [0, 37, 59, 60, 82]`, correct only for one particular point count;
change `_fairing_pts` and those indices silently address the wrong vertices,
which presents as a fold that looks like a kernel bug. `swsplineparts.landmarks`
finds them geometrically (LE, both crests, both TE-face points). Reassuringly it
returns exactly `[0, 37, 59, 60, 82]` on the current section.

### The trap: one closed spline ROUNDS THE TRAILING EDGE AWAY

The first spline fairing came out **2.0 % under volume**. Cause: it was built as
a single closed spline through all 119 points. `frame/model.py::_section_wire`
warns about precisely this:

> *"The TE is a straight LINE, never part of the spline. `te_thickness` exists
> to fix the separation line with a defined blunt edge; running one closed
> spline through it rounds that away."*

That edge is the one `studies/tethin1.yaml` is solving, so softening it would
have quietly invalidated the study. Sections are now built the model's way:
upper spline LE→TE, a straight **line** across the blunt face, lower spline back
to the shared LE point.

### Accuracy, against an independent reference

Neither SolidWorks build is the arbiter, so the section area was integrated
along the span analytically (shoelace per station, trapezoid over stations,
minus the rod bore):

| part | reference | polyline | spline | |
|---|---:|---:|---:|---|
| fairing | 6624.0 | 6733.3 (**+1.65 %**) | 6584.6 (**−0.59 %**) | spline 2.8× closer |
| stub | 1629.8 | 1623.9 (**−0.36 %**) | 1630.7 (**+0.06 %**) | spline 6.6× closer |

The polyline fairing was **oversize**, which is the signature of the loft
overshooting and folding — a fold adds material.

### `core_native` stays a polyline, and this is the important one

The core's hub is `S.superellipse(ax, ay, section_n, 56)` — a genuine curve
drawn as 56 straight segments — so it looked like the obvious next conversion.
It was done: a C# spline extrude gave a hub of **3 faces** and a volume of
14321.8 mm³ against a true superellipse of **14320.9 (+0.006 %)**, where the
56-gon inscribes at 14295.1 (**−0.18 %**). Thirty times more accurate.

**It was then reverted**, because accuracy was the wrong test:

```
model core_body volume    20733.3 mm3
  polyline core_native    20774.3   (+0.20 %)
  spline   core_native    20678.4   (−0.26 %)
```

`frame/model.py::core_body` builds that hub with
`Polyline(*pts, close=True)` — **the model's own core hub is a 56-gon.** So the
SolidWorks polyline MATCHED the model and the spline version DIVERGED from it.

This is the distinction that makes the whole exercise meaningful. The pod,
fuselage and fairing carry `profile_curve: spline` / `section_curve: spline` in
`params.yaml`; there the polyline was an *approximation of what the model
actually builds*, and removing it closed a gap. The core carries no such
setting; there the polyline *is* what the model builds, and "improving" it
unilaterally would leave two representations that disagree by construction —
destroying the only thing that makes a second representation a check
(skill rule 16).

**The open question is a design one, not a modelling one:** should the model's
core hub be a spline too? That is Ben's call, and it must change in BOTH places
or neither. Filed in `docs/TODO.md`.

## 2026-09-26 (evening) — command engine M1/M2: measured on SW 2024 SP3.1 (32.3.1)

Found by `swengine/` (typed C# host, `docs/solidworks-command-engine-design.md`)
against live SolidWorks. Each item is from a real run.

1. **Binding works as designed.** A single `SLDWORKS.exe` in the session,
   `Marshal.GetActiveObject`, then `ISldWorks.GetProcessID()` == that PID
   (4840, later 1004 after a restart). A `Start-Process` launch registered in
   the ROT and attached on the first probe.
2. **The default part template on this seat is IPS.** `swDefaultTemplatePart` →
   `C:\ProgramData\SolidWorks\SOLIDWORKS 2024\templates\Part.PRTDOT`, whose
   `swUnitsLinear` is 3 (inches). The legacy tools set MMGS per document
   (`swsetup.cs SetMm`). The engine instead pins an MMGS template made from it
   (`swengine template-install --id part-mmgs-lab-v1`) and refuses any
   template whose linear unit is not mm.
3. **`InsertSketch` opens nothing in a document created hidden.** Under
   `DocumentVisible(false)`, `NewDocument` returns a part. A datum plane selects
   fine, with 1 object of type `swSelDATUMPLANES`, but `SketchManager.InsertSketch(true)`
   leaves `ActiveSketch` null. Build the candidate visible.
4. **STL export of a hidden, non-active document faults inside SolidWorks.**
   `Extension.SaveAs(...stl, Silent|Copy)` on a hidden read-only reopen threw
   `RPC_E_SERVERFAULT (0x80010105)` after 3.5 s, while STEP from the same
   document succeeded. This is §8.9's "the STL translator follows the ACTIVE
   document". With the candidate reopened visible and active it works, in 94 ms.
   The engine now refuses to export unless the candidate is `ActiveDoc`.
5. **STL export preferences are SI.** The defaults read back `swSTLDeviation` =
   0.00024 (m) and `swSTLAngleTolerance` = 0.17453 (rad, i.e. 10°). The engine
   exports with 1e-5 m / 0.05 rad, which gives 10 840 triangles on the pod.
   `PreferenceScope` restored every value after both the fault and success.
6. **SolidWorks writes `x.STL` when asked for `x.stl`.** This is harmless on NTFS.
   The engine records the on-disk name.
7. **The STL is tessellated face by face.** Where the spline face meets a flat,
   the shared boundary vertices differ in the last float32 bits: 128 of 5550
   vertices, which gives 258 bitwise-open directed edges. After a 1e-4 mm weld
   it is closed and consistently oriented. Every vertex lies within 0.00048 mm
   of the OCCT reference.
8. **The mass-property volume reads 5.0e-5 low.** For the engine pod SolidWorks
   reports 17015.409 mm³. OCCT gives 17016.268 mm³ for the STEP export of the
   same part, against a reference of 17016.262. That is SolidWorks'
   mass-property accuracy, not geometry: the legacy `pod_native` reads the same
   17015.408. It is inside the 0.05 % gate, but don't tighten that gate below
   ~1e-4 without raising the mass-property accuracy.
9. **Exact radius probes: `IFace2.GetProjectedPointOn(point, dir)`.** Project
   (0.1 m, y, 0) along −X onto the revolved face. It is exact at the station,
   unlike a closest-point query on a sloped face. All 7 stations matched the
   OCCT section-area radii to ≤ 0.00018 mm. `ISurface.PlaneParams` is
   [normal xyz, point xyz] in metres; the flat radius comes from `GetArea`.
10. **Selecting by object works where selecting by name was the only way
    before.** `IRefPlane.Transform.ArrayData` identifies the XY plane (identity)
    without its English name. `IFeature.Select2(false, 0)` on the plane, then on
    the sketch (cast from `ActiveSketch`), gives exactly 1 selected object, and
    `FeatureRevolve2` uses the sketch's single centreline as the axis.
11. **Not yet provoked: busy rejection.** The OLE message filter recorded 0
    retries in every run. A deliberately busy session is still an open M1
    qualification item.

## 2026-09-26 (night) — command engine M3: assemblies, measured

12. **The transform storage order is qualified by SolidWorks itself.** A
    component inserted with `Transform2` set to `RigidTransform.ToSolidWorksArray()`
    (rotation written TRANSPOSED, translation in metres) carries the landmark
    (1, 2, 3) mm to (8, 21, 33) mm under Rz(+90°) + (10, 20, 30) mm. The mapped
    point comes from SolidWorks' own `MathPoint.MultiplyTransform(comp.Transform2)`,
    and matches to 3.6e-15 mm before and after save and reopen. `swasm.py`'s
    empirical transpose was right; the "row-major" comment in §4.11 describes
    the array's rows, which hold the transpose of the column-vector R.
    `Transform2` reads back equal to the written array within 3.5e-18.
13. **`AddComponent5` + overwriting `Transform2` + `FixComponent` works for the
    4 station pods.** Tip and motor-face centres land within 7e-15 mm of the
    model's own placed `nacelle_mount` solids. That is independent of the
    transform math, and was confirmed in OCCT from the assembly STEP.
    `InterferenceDetectionManager` (coincidence not counted) reports 0.
    `Component2.GetPathName()` after reopen resolves to the job's own
    `artifacts/parts/pod.SLDPRT`. The sealed part's bytes are unchanged after
    save, reopen and export.
14. **Reference planes renamed to misleading names change nothing.** A template
    whose three planes are `Datum-C/A/B` builds a pod whose STL is
    byte-identical to the golden pod (`8115ab9a29c2`). This confirms that selecting
    by `IRefPlane.Transform` identity is independent of names (AUD-13).
15. **Timing.** A 4-pod assembly takes a median of 3.9 s: part load 0.62 s,
    4× add+fix 0.52 s, reopen 0.87 s, each measure 0.53 s. A batch of 10 in one
    host session took 38 s.

## 2026-09-26 (late) — command engine M4: the arm fairing, measured

16. **`InsertProtrusionBlend`: `Merge` is the 15th argument.** The order is
    `(Closed, KeepTangency, ForceNonRational, TessToleranceFactor,
    StartMatchingType, EndMatchingType, StartTangentLength, EndTangentLength,
    StartTangentDir, EndTangentDir, IsThinBody, Thickness1, Thickness2,
    ThinType, Merge, UseFeatScope, UseAutoSelect)`. Passing `false` 10th
    toggled a tangent direction and still merged the tool loft into the part.
    Read parameter names by reflection (`GetParameters()`) before trusting any
    positional call.
17. **A body cut by an unmerged loft plus `InsertCombineFeature(SWBODYCUT, main,
    [tool])` returns null.** It fails the same way the pod pocket's combine did in
    `swnative.py`. **`InsertCutBlend`** (a lofted cut through the selected 3D-sketch
    profiles) does the job as one native feature: 25 closed-spline keepout
    rings in 11–12 s.
18. **`FeatureCut4`'s `Dir` on a sketch in a +Z distance plane:** `false` cuts
    toward −Z and `true` toward +Z. `InsertRefPlane(Distance, d)` off the XY plane
    landed at +d with its normal along +Z. Both were verified by the part's
    extents after the cut, not assumed. The engine checks max z and min z
    around every one-sided cut.
19. **`IBody2.GetExtremePoint` is a local search on spline faces.** On the
    fairing, the +Y extreme came back as 5.700, which is the upper surface at the
    outboard edge. The true maximum is 5.797 at z 38, and the engine's own ray
    samples reproduced it to 1e-4. The −Y extreme was exact. Use it only
    where the extent is bounded by a plane.
20. **3D-sketch loft timing on this seat.** 21 fairing sections of 2 splines
    + 1 line (119 points) take 13–14 s to sketch and loft. A 4-hand fairing job
    runs about 83 s end to end. OCCT ray-sampled thickness and root height agree
    to ≤ 0.0013 mm, and the independent bidirectional surface distance is
    0.0023–0.0030 mm. SolidWorks' blend and OCCT's loft through the same
    sections are the same surface to within 3 µm.

## 2026-09-26 (late night) — M4 stub, core and full airframe, measured

21. **Scope `AddToDB` on EVERY planar sketch, not just 3D sketches.** Without
    it, SolidWorks' sketch inference snaps new points onto nearby entities. The
    core hub's 56-edge polygon came out **2.2 % small** (998.8 vs 1021.1 mm²),
    which cost −112 mm³ of the core. A per-step volume trace found it in one run.
22. **A plane through three sketch points needs selection MARKS 0, 1, 2.**
    `InsertRefPlane(Coincident, 0, Coincident, 0, Coincident, 0)` returns null
    when the points are selected with the default mark. Use `SelectData.Mark = i`.
    Verify the plane against the points. Read the normal from `Transform.ArrayData[6..8]`
    and the origin from `[9..11]`.
23. **Sketch on any plane in MODEL coordinates** with
    `ISketch.ModelToSketchTransform` and `MathPoint.MultiplyTransform`. That is how the oblique
    motor pocket is drawn.
24. **Extrude direction flags differ for cut and boss.** On a sketch whose plane
    normal is +Z, `FeatureCut4` with Dir=false cuts toward −Z, and
    `FeatureExtrusion3` with Dir=true grows toward −Z. The engine reads each
    plane's normal and chooses the flag from it (`BossDirFor`). Every one-sided
    op is checked afterwards by extents or a ray.
25. **Flush trim to a skin:** loft a SURFACE through the fuselage rings
    (`InsertLoftRefSurface2`), cut with it (`IFeatureManager.InsertCutSurface`;
    Flip=true keeps the inside of this tube), then `InsertDeleteBody2` the
    surface body. The collars come out flush to 0.00034 mm (OCCT).
26. **SolidWorks' blend and OCCT's loft differ at a loft END by up to 0.19 mm**
    through the same 21 sections. This shows on the stub, in the last span,
    where the tip flare (u²) changes fastest. **Guide curves fix it.** The three
    spanwise edges of the reference loft (LE and both TE corners), sampled
    densely plus each section's vertex and selected with mark 2, bring it to
    0.0205 mm unmasked. The LE guide alone reached 0.081 mm.
27. **`InterferenceDetectionMgr.GetInterferences()` → `IInterference.Components`
    and `.Volume` name each pair.** A fairing and its stub share one transform, so
    assembly checks match components to instances by PART first, then by
    position.
28. **Geometry facts found by the jig check.** The 20×20 stack bolt pattern
    (±10, ±10) lies exactly on the arm diagonals, so the model's 60 mm stack
    holes pass through the rod bores, and pins there hit the rods. The lowest
    point of the aircraft is the aft rail ends (z −34), below the bell tops
    (−27.6). The bell protrudes only 0.6 mm below the pod's bottom ring.

### 2026-09-27 — a cut that misses the part returns NULL

`FeatureCut4` with a blind depth whose tool never intersects the body returns
**null**. It is not an empty feature, and not a no-op. Found when the core recipe was asked to cut
the RL/RR motor-lead slots, which pass clear of the core. The engine treats null
as REBUILD_FAILED (correct: fail closed). Emit a cut only when the model says it
removes material (`export_core.py` checks `slot ∩ core > 0`).

## 2026-10-04 — core v2 (rev0), measured; an open document with the same TITLE quarantines the engine

**`part.build_core@2`** (the rev0 flat-stack core) built first time on SW 2024 SP3.1. It passed
234/234 checks (117 on the candidate, 117 after reopen) with zero session drift and zero busy
retries, in about 3 min, most of it in `measure_candidate` (112 ray samples, 134 s). Two
primitives are new: `AddCircles` and `CutCircles` over a `CircleGroup`. Each one proves its own
direction with a ray down its axis. A cut must reach the floor at `5 + depth`, and a boss must
show its base at `5`, so a feature built the wrong way fails inside its step.

**The trap.** The first run built everything and passed all 117 candidate checks. It then
quarantined at `reopen` with `COM_OUTCOME_UNKNOWN: candidate still open after QuitDoc:
core.SLDPRT`. A *review* set staged by `swreview_cowlscrews.py` was still open in the same
session, and its part was also called `core.SLDPRT`. SolidWorks identifies documents by
**title**, not path: the engine's "is my candidate closed?" test saw the other file, and
session drift showed the review core's path flip to the job's artifact.

**Rule:**
- Before a live engine job, `host --probe`.
- If any open document shares a title with the part being built, close it first
  (`closeall.vbs` once the probe shows nothing dirty).
- Clear the quarantine with `recover --reviewer <who> --close-engine-documents`.

The quarantine was the right response: the engine could not prove which document it was
closing, so it refused to replay.

### 2026-10-04 — the rail: a countersink as a revolve cut, and through-holes

`part.build_rail@1` passed **146/146 on its first live run**. Two new pieces of
SolidWorks-side checking:

- **`CutConeFeature` (`ConeCut`).** A countersink is a `FeatureRevolve2` cut. Its profile is a
  closed polygon on a plane through the axis, with one centreline on the axis, as in the pod
  revolve. The profile starts 0.5 mm *outside* the face so the cut never shares the face plane.
  - **Direction check:** a ray parallel to the axis, mid-way between the two radii, must meet
    the cone wall **strictly** past the face (t > 5.01).
  - **Why strictly:** a cone cut on the wrong side leaves the face whole, so the ray meets it at
    exactly 5. An inclusive bound would pass that.
- **`CircleGroup.through`.** A through-hole has no floor, so the floor ray (`5 + depth`) cannot
  check it. A through group requires the axis ray to meet **nothing**.

The circle-group, box and cone helpers now live on `SwLoftedPart` and are shared by the core
and the rail.

### 2026-10-04 — cowl v2: cap the CAVITY, not the shell

`part.build_cowl@2` (rev0 cowls: + rail ribs, + J5/J6 clearance holes) passed **first
time on both pieces**: fwd 682/682 (job 1b7cd96e), aft 610/610 (job 090cabcc), about 5 min for the pair.

**The v1 recipe could not build the rev0 nose.**
- **What v1 did:** cut the cavity loft through both tips, then bossed a slab, one wall thick,
  back from the skin's end ring.
- **Why it can't work here:** that only closes the cavity if the skin grows by no more than the
  wall over the slab. rev0's fat nose grows **1.49 mm over a 1.26 wall**, so the exporter
  refused it ("cap at z 87.5").
- **v2 does what the model does:** the cavity loft **stops one wall short of each end**. Its
  two end rings are sampled from the model's inset loft exactly at z0 + wall and z1 − wall.
  It has no slabs and no end-ring assumption, so it works for any nose or tail.
- **Proved offline before SolidWorks:** a build123d replay of the JSON matched the model at
  −0.04 % (fwd) / −0.08 % (aft) volume, with all 636 rays ≤ 0.0002 mm.

**Two further notes:**
- **Ribs:** `AddRib` bosses a box that roots in the wall. The check is one solid after, and a
  volume gain between 20 % and 100 % of the box (the wall already holds part of it).
- **Through-holes:** "through" now means *clear over the cut depth*. Through a cowl wall the
  axis ray goes on across the cavity and meets the far wall. That is correct, and the rail's
  strict "nothing at all" check would have failed it.

### 2026-10-04 — the cowl's ring curves: two kernels, one set of points, 0.09 mm apart

The first v2 cowls passed every engine check (682/682, 610/610) and then **failed the OCCT
verifier**: 0.093 / 0.096 mm surface and STL deviation against a 0.05 gate.

**Where:** two lines along the whole length at the **belly apex** of the n5 superellipse
(x 26.65, y ±2.7). Each ring is a closed spline through 56 formula points, and SolidWorks'
spline and OCCT's interpolate differently **between** the points where the section is
flattest. Because it was in the ring curves, not the loft, it appeared at every z.

**Why the engine missed it:** its skin rays ran every 30°, and the 0° ray lands *on* a ring
point, where the kernels agree by construction. The build123d JSON replay could not see it
either, because it lofted in the same kernel as the model.

**Fix: pin SolidWorks to the reference surface.**
1. Every ring interval gets a point **sampled from the model's own loft** (a ray cast at the
   bisecting angle), giving 112 points.
2. Intervals within 25° of an apex get **3** sampled points.

| rings | fwd surface / STL vertex | aft surface / STL vertex |
|---|---|---|
| 56 formula points | 0.093 / 0.093 | 0.096 / 0.096 |
| + 1 sampled per interval (112) | 0.008 / 0.049 | 0.010 / **0.052 ✗** |
| + 3 per interval near the apexes | 0.0075 / **0.025** | 0.0101 / **0.028** |

**The engine now checks this itself:** 336 extra rays per piece at the ring **mid-angles**
(skin and cavity, 3 stations). They find 12/672 off on the 56-point build and 0 on the final.

**Final:** core 266b8f68 (layout B, M2×4 inserts) 328/328; cowl-fwd 5bc58d75 1354/1354; cowl-aft b76619db
1258/1258. All three pass OCCT. Native fit with the rods: 8 parts, 28 pairs, 0 clashes.

### 2026-10-04 — part.build_prismatic, and a boss check that knows what is behind it

**What it is:** `part.build_prismatic@1` builds jigs and fixtures from an ordered list of
add/cut prisms and add/cut circle groups. That is the model's own list, which
`model.prismatic_solid` also builds.

**The new primitive is `AddPrism`:**
- The **first** prism makes the body. It must equal its polygon area × depth, and its extreme
  along Dir must be the plane plus the depth (a wrong-way extrude fails here).
- **Later** prisms must merge into one solid and add no more than their own volume.

**The assembly jig (14 features) failed on its first live run, inside the engine's own check.**
`AddCircleGroup` proved a boss's direction by seeing its **base** at t = 5 from 5 mm behind
the plane. The jig's posts stand **on a bar**, so that ray met the bar's underside at t = 1.
- **The check now:** the base from behind (t = 5) **or** the tip from 5 mm beyond the end,
  looking back (t = 5).
- **Why it still catches a wrong-way boss:** that fails both. The core's standoffs pass from
  behind (open air there); their tips are inside the hub. The jig's posts pass from beyond.
- **Result:** the rebuild passed 270/270, and the OCCT verifier was exact.

### 2026-10-06 — the full native airframe assembly, and three things that blocked it

`assembly.build` placed **82 components from 34 native parts** and passed 1218/1218, including
SolidWorks interference detection.

**Overlaps:**
- **The rule:** every overlap must be declared with the model's volume. Matching within 1 % passes;
  anything undeclared fails.
- **How they are declared:** the exporter computes them from the model's own placed solids rather
  than listing them by hand. It found 10, all screw shanks threaded into their inserts, and SolidWorks
  found exactly those.

**What blocked it, in order:**
1. **A landmark that assumed one end face.** The fairing landmark looked for *one* planar face at the
   outboard radius. The ID letter **R** has a closed counter, which leaves an island of end face inside
   it: a second face at the same radius. **Now:** take the largest.
2. **zsh does not word-split `$VAR`.** Thirty-four `--input` flags arrived as one argument. The same
   cause earlier broke `export -f` for a parallel verifier. **Now:** build argv lists in Python, or put
   loops in a bash script file.
3. **Two runaway guards**, both last raised for the 17-part airframe:
   - `EngineLimits.MaxInputs` 32 → **64**
   - `assembly.build` parts 32 → **64**

   **Run `plan` before `submit`.** It runs every engine validation with zero SolidWorks calls, and
   would have caught both.

**Also new:** `part.build_prismatic` accepts a circle group as its first, body-making feature (a rod,
a pin), and `AddCircleGroup` handles an empty part.

### 2026-10-06 — one solid after EVERY cut: cut order matters even when the result does not

The pod pieces' `cut_slots` step checks the body count after each prism (`CutPrism`), not at
the end of the step.

- **What happened:** the lead exit window is two prisms (row, ramp). The model cut their
  **union** and the mount came out one solid. In SolidWorks the **row alone** left a 0.49 mm³
  crumb of mount, which the ramp would have taken next. All four mounts failed:
  *"slot lead-exit-row left 2 solids"*.
- **Fix:** cut the ramp first (`model.wire_exit_prisms` returns them in cut order).
- **Guard:** selftest now replays the lead path cut by cut on the bare pieces and checks one solid
  after each.

**Rule:** when the exporter splits one model cut into several prisms, either keep the order the
model cuts them in, or check the body count after each one in the model too. A union that is one
solid says nothing about its parts.

**Related:** a cut that removes nothing is also refused ("removed no material"). The exporter
now gives each pod piece only the slot and window prisms that reach it (the flat slot never
touches the shroud).

### 2026-10-08 — rounded prism corners: `Create3PointArc` in the prism sketch

`PrismCut.corner_radii_mm` (optional, one per corner, 0 = sharp) rounds a prism's corners.
This is the stress-riser survey's lead slot, exit window and core wire-pass notches.

- **How:** `PrismCut.CornerArcs()` (Contracts) computes, per rounded corner, the tangent point on each edge
  (r / tan(θ/2) from the corner) and the arc's midpoint on the bisector. `CutPrism` draws each edge
  tangent point to tangent point with `CreateLine`, and each corner with
  `SketchManager.Create3PointArc(start, end, mid)`. Python (`model.rounded_corner_arcs`) does the same
  arithmetic, and `Edge.make_three_point_arc` builds the reference.
- **Worked first time:** the core, 4 mounts and 4 stubs passed every engine check and OCCT verification
  with no sketch-relation or closure trouble. The endpoints are equal to 1e-9, as with the straight
  polygons.
- **Validation:** a radius must fit its two edges along with the neighbours' tangent lengths. A straight or
  reversed corner cannot be rounded. Both refusals happen in `PrismCut.Validate`, before any CAD runs.
