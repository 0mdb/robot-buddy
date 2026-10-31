// swbuild.exe <manifest>
//
// Small SolidWorks command engine for robot-buddy's chassis. tools/chassis.py
// owns the geometry and writes the manifest; this file owns SolidWorks.
// Rules it follows (docs/cad/solidworks-api.md, .claude/skills/solidworks):
//   C# 5, [STAThread], attach to a hand-started SolidWorks, never LoadFile,
//   always set Transform2, measure after every feature, trust the last line.
//
// Manifest: one command per line, fields separated by '|', lengths in mm.
//   part|<out.SLDPRT>                         new part (MMGS template default)
//   box|x0 x1|y0 y1|z0 z1                     boss: rectangle on Front, along Z
//   cyl|x|y|z axis|c1 c2|a0 a1|r|boss|cut     cylinder along an axis
//                                             (c1 c2 = the other two coords in
//                                             x,y,z order; a0 a1 = span, or
//                                             'all' for a through cut)
//   prof|z0 z1|<segs>[|cut|all]               closed profile on Front, along Z
//                                             (boss, blind cut, or through cut).
//                                             segs: 'M x y' start, 'L x y' line,
//                                             'A cx cy x y' arc (CCW), space-sep
//   expect|vol <mm3> <tol>|box x0 x1 y0 y1 z0 z1 <tol>
//   save
//   asm|<out.SLDASM>
//   comp|<name>|<path>|r00 r01 r02 r10 r11 r12 r20 r21 r22 tx ty tz|fix
//   interfere                                 list interferences in the asm
//   asmsave
//   shot|<doc>|<outprefix>                    iso/top/front/right BMPs
//   close|<doc>                               close a document this run opened
//   fillet|r|x|y|z|any|x0 y0 z0 x1 y1 z1|n|dvol tol
//                                             constant-radius fillet on the LINEAR edges
//                                             parallel to the axis whose midpoint is in the
//                                             box; expects exactly n edges and a volume
//                                             change of dvol +- tol (mm3, + = concave)
//   ring|z0 z1|<loop>|<loop>|boss|cut         annulus on Front about the Z axis, along Z.
//                                             loop: "c R" circle, or "p r0 r1 .. rn-1" a
//                                             polyline through radii at equal angles from
//                                             theta = 0 (tools/drivetrain.py's polar curves)
//   stl|<doc.SLDPRT>|<out.stl>                binary STL, mm, fine, in the part's own
//                                             coordinates (not shifted to positive space)
//   rotbody|px py pz|y|deg                    rotate every solid body about the axis
//                                             through (px,py,pz) parallel to Y (Move/Copy Body)
// Ends with "BUILD OK" or "BUILD FAILED n".
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

class SwBuild
{
    static CultureInfo ci = CultureInfo.InvariantCulture;
    static ISldWorks sw;
    static int failures = 0;
    static IModelDoc2 doc;      // current part
    static IModelDoc2 asmDoc;   // current assembly
    static string docPath, asmPath;

    static void Check(string what, bool ok, string detail)
    {
        Console.WriteLine((ok ? "  ok   " : "  FAIL ") + what + "  " + detail);
        if (!ok) failures++;
    }

    static double[] Nums(string s)
    {
        string[] t = s.Split(new char[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
        double[] d = new double[t.Length];
        for (int i = 0; i < t.Length; i++) d[i] = double.Parse(t[i], ci);
        return d;
    }

    static double M(double mm) { return mm / 1000.0; }

    [STAThread]
    static int Main(string[] args)
    {
        try { return Run(args); }
        catch (Exception ex)
        {
            Console.WriteLine("FATAL " + ex.GetType().Name + ": " + ex.Message);
            Console.WriteLine(ex.StackTrace);
            Console.WriteLine("BUILD FAILED fatal");
            return 99;
        }
    }

    static int Run(string[] args)
    {
        for (int i = 0; i < 30 && sw == null; i++)
        {
            try { sw = (ISldWorks)Marshal.GetActiveObject("SldWorks.Application"); }
            catch (COMException) { System.Threading.Thread.Sleep(1000); }
        }
        if (sw == null) throw new Exception("no SOLIDWORKS in the ROT (start it by hand)");
        Console.WriteLine("SOLIDWORKS " + sw.RevisionNumber());

        foreach (string raw in File.ReadAllLines(args[0]))
        {
            string line = raw.Trim();
            if (line.Length == 0 || line.StartsWith("#")) continue;
            string[] f = line.Split('|');
            for (int i = 0; i < f.Length; i++) f[i] = f[i].Trim();
            switch (f[0])
            {
                case "part": NewPart(f[1]); break;
                case "box": Box(f); break;
                case "cyl": Cyl(f); break;
                case "prof": Prof(f); break;
                case "expect": Expect(f); break;
                case "save": SavePart(); break;
                case "asm": NewAsm(f[1]); break;
                case "comp": Comp(f); break;
                case "interfere": Interfere(); break;
                case "asmsave": SaveAsm(); break;
                case "shot": Shot(f[1], f[2]); break;
                case "close": CloseByPath(f[1]); break;
                case "rotbody": RotBody(f); break;
                case "stl": Stl(f[1], f[2]); break;
                case "fillet": Fillet(f); break;
                case "filletface": FilletFace(f); break;
                case "ring": Ring(f); break;
                default: Check("command " + f[0], false, "unknown"); break;
            }
            if (failures > 0 && f[0] != "expect") break;   // stop at the first broken step
        }
        Console.WriteLine(failures == 0 ? "BUILD OK" : "BUILD FAILED " + failures);
        return failures == 0 ? 0 : 1;
    }

    // ---------------------------------------------------------------- parts
    static void NewPart(string path)
    {
        string tmpl = sw.GetUserPreferenceStringValue(
            (int)swUserPreferenceStringValue_e.swDefaultTemplatePart);
        doc = (IModelDoc2)sw.NewDocument(tmpl, 0, 0, 0);
        docPath = path;
        Check("new part " + Path.GetFileName(path), doc != null, tmpl);
        if (doc == null) return;
        // millimetres for whoever opens it by hand
        doc.Extension.SetUserPreferenceInteger(
            (int)swUserPreferenceIntegerValue_e.swUnitSystem, 0,
            (int)swUnitSystem_e.swUnitSystem_MMGS);
    }

    static bool Sketch(string plane)
    {
        doc.ClearSelection2(true);
        string name = plane == "front" ? "Front Plane" : plane == "top" ? "Top Plane" : "Right Plane";
        if (!doc.Extension.SelectByID2(name, "PLANE", 0, 0, 0, false, 0, null, 0))
        { Check("select " + name, false, ""); return false; }
        doc.SketchManager.InsertSketch(true);
        doc.SketchManager.AddToDB = true;
        return true;
    }

    static void CloseSketch()
    {
        doc.SketchManager.AddToDB = false;
        doc.SketchManager.InsertSketch(true);
    }

    // Extrude the just-closed sketch from 'a0' to 'a1' along the plane normal.
    // Measured mapping (solidworks-api.md): Front +Z, Top +Y, Right +X.
    static IFeature Extrude(double a0, double a1, bool cut, bool through)
    {
        IFeatureManager fm = doc.FeatureManager;
        if (through)
            return (IFeature)fm.FeatureCut4(false, false, false, 1, 1, 0.01, 0.01,
                false, false, false, false, 0.0, 0.0, false, false, false, false,
                false, true, true, true, true, false, 0, 0.0, false, false);
        double len = a1 - a0;
        int t0 = Math.Abs(a0) < 1e-9 ? 0 : 3;          // 3 = swStartOffset
        bool flipStart = a0 < 0;
        // A blind cut runs AGAINST the plane normal unless Dir is set (measured
        // 2026-10-30: Front-plane cut 0..4.7 went to -Z and returned null).
        if (cut)
            return (IFeature)fm.FeatureCut4(true, false, true, 0, 0, M(len), 0.0,
                false, false, false, false, 0.0, 0.0, false, false, false, false,
                false, true, true, true, true, false, t0, M(Math.Abs(a0)), flipStart, false);
        return (IFeature)fm.FeatureExtrusion3(true, false, false, 0, 0, M(len), 0.0,
            false, false, false, false, 0.0, 0.0, false, false, false, false,
            true, true, true, t0, M(Math.Abs(a0)), flipStart);
    }

    static void After(string what, IFeature feat)
    {
        doc.EditRebuild3();
        Check(what, feat != null, feat == null ? "feature null" : Measure());
    }

    static void Box(string[] f)
    {
        double[] x = Nums(f[1]), y = Nums(f[2]), z = Nums(f[3]);
        if (!Sketch("front")) return;
        doc.SketchManager.CreateCornerRectangle(M(x[0]), M(y[0]), 0, M(x[1]), M(y[1]), 0);
        CloseSketch();
        After("box " + f[1] + " | " + f[2] + " | " + f[3], Extrude(z[0], z[1], false, false));
    }

    static void Cyl(string[] f)
    {
        string ax = f[1];
        double[] c = Nums(f[2]);
        bool through = f[3] == "all";
        double[] a = through ? new double[] { 0, 0 } : Nums(f[3]);
        double r = double.Parse(f[4], ci);
        bool cut = f[5] == "cut";
        // sketch-plane coordinates per the measured mapping:
        //   z axis -> Front: (x, y) ; y axis -> Top: (x, -z) ; x axis -> Right: (-z, y)
        string plane; double u, v;
        if (ax == "z") { plane = "front"; u = c[0]; v = c[1]; }
        else if (ax == "y") { plane = "top"; u = c[0]; v = -c[1]; }
        else { plane = "right"; u = -c[1]; v = c[0]; }
        if (!Sketch(plane)) return;
        doc.SketchManager.CreateCircleByRadius(M(u), M(v), 0, M(r));
        CloseSketch();
        After("cyl " + ax + " " + f[2] + " | " + f[3] + " r" + f[4] + " " + f[5],
              Extrude(a[0], a[1], cut, through));
    }

    static void Prof(string[] f)
    {
        double[] z = Nums(f[1]);
        string[] t = f[2].Split(new char[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
        // optional 5th field: sketch plane. Coordinates are SKETCH coordinates:
        // front (x, y) -> extrude +Z; right (-z, y) -> extrude +X (measured mapping)
        string plane = f.Length > 4 ? f[4] : "front";
        if (!Sketch(plane)) return;
        ISketchManager sm = doc.SketchManager;
        double px = 0, py = 0, sx = 0, sy = 0; int i = 0, segs = 0;
        while (i < t.Length)
        {
            string k = t[i];
            if (k == "M") { px = sx = double.Parse(t[i + 1], ci); py = sy = double.Parse(t[i + 2], ci); i += 3; }
            else if (k == "L")
            {
                double x = double.Parse(t[i + 1], ci), y = double.Parse(t[i + 2], ci);
                sm.CreateLine(M(px), M(py), 0, M(x), M(y), 0); px = x; py = y; i += 3; segs++;
            }
            else if (k == "A")
            {
                double cx = double.Parse(t[i + 1], ci), cy = double.Parse(t[i + 2], ci);
                double x = double.Parse(t[i + 3], ci), y = double.Parse(t[i + 4], ci);
                sm.CreateArc(M(cx), M(cy), 0, M(px), M(py), 0, M(x), M(y), 0, 1);
                px = x; py = y; i += 5; segs++;
            }
            else { Check("prof token " + k, false, ""); return; }
        }
        if (Math.Abs(px - sx) > 1e-6 || Math.Abs(py - sy) > 1e-6)
            sm.CreateLine(M(px), M(py), 0, M(sx), M(sy), 0);
        CloseSketch();
        bool cut = f.Length > 3 && (f[3] == "cut" || f[3] == "all");
        After("prof " + plane + " " + segs + " segs span " + f[1] + (cut ? " " + f[3] : ""),
              Extrude(z[0], z[1], cut, f.Length > 3 && f[3] == "all"));
    }

    static string Measure()
    {
        object[] bodies = (object[])((IPartDoc)doc).GetBodies2((int)swBodyType_e.swSolidBody, true);
        int nb = bodies == null ? 0 : bodies.Length;
        double[] b = (double[])((IPartDoc)doc).GetPartBox(true);
        IMassProperty mp = (IMassProperty)doc.Extension.CreateMassProperty();
        return string.Format(ci, "bodies {0}  vol {1:F1} mm3  box X[{2:F2},{3:F2}] Y[{4:F2},{5:F2}] Z[{6:F2},{7:F2}]",
            nb, mp.Volume * 1e9, b[0] * 1e3, b[3] * 1e3, b[1] * 1e3, b[4] * 1e3, b[2] * 1e3, b[5] * 1e3);
    }

    static void Expect(string[] f)
    {
        IPartDoc pd = (IPartDoc)doc;
        object[] bodies = (object[])pd.GetBodies2((int)swBodyType_e.swSolidBody, true);
        int nb = bodies == null ? 0 : bodies.Length;
        Check("one solid body", nb == 1, nb + " bodies");
        for (int k = 1; k < f.Length; k++)
        {
            double[] v = Nums(f[k].Substring(f[k].IndexOf(' ') + 1));
            if (f[k].StartsWith("vol"))
            {
                IMassProperty mp = (IMassProperty)doc.Extension.CreateMassProperty();
                double vol = mp.Volume * 1e9;
                Check("volume", Math.Abs(vol - v[0]) <= v[1],
                      string.Format(ci, "{0:F1} vs {1:F1} mm3 (tol {2})", vol, v[0], v[1]));
            }
            else if (f[k].StartsWith("box"))
            {
                double[] b = (double[])pd.GetPartBox(true);
                double[] got = { b[0] * 1e3, b[3] * 1e3, b[1] * 1e3, b[4] * 1e3, b[2] * 1e3, b[5] * 1e3 };
                double worst = 0;
                for (int i = 0; i < 6; i++) worst = Math.Max(worst, Math.Abs(got[i] - v[i]));
                Check("box", worst <= v[6], string.Format(ci, "worst axis error {0:F3} mm", worst));
            }
        }
    }

    static void SavePart()
    {
        // T3: one machine-readable line per part; chassis.py applies density and placement
        IMassProperty mp = (IMassProperty)doc.Extension.CreateMassProperty();
        double[] com = (double[])mp.CenterOfMass;
        Console.WriteLine(string.Format(ci, "MASS|{0}|{1:F1}|{2:F3} {3:F3} {4:F3}",
            Path.GetFileName(docPath), mp.Volume * 1e9, com[0] * 1e3, com[1] * 1e3, com[2] * 1e3));
        int e = 0, w = 0;
        bool ok = doc.Extension.SaveAs(docPath, (int)swSaveAsVersion_e.swSaveAsCurrentVersion,
            (int)swSaveAsOptions_e.swSaveAsOptions_Silent, null, ref e, ref w);
        Check("save " + Path.GetFileName(docPath), ok, "err " + e + " warn " + w);
        sw.CloseDoc(doc.GetTitle());
        doc = null;
    }

    // ----------------------------------------------------------- assemblies
    static void NewAsm(string path)
    {
        string tmpl = sw.GetUserPreferenceStringValue(
            (int)swUserPreferenceStringValue_e.swDefaultTemplateAssembly);
        asmDoc = (IModelDoc2)sw.NewDocument(tmpl, 0, 0, 0);
        asmPath = path;
        Check("new assembly " + Path.GetFileName(path), asmDoc != null, tmpl);
        if (asmDoc != null)
            asmDoc.Extension.SetUserPreferenceInteger(
                (int)swUserPreferenceIntegerValue_e.swUnitSystem, 0,
                (int)swUnitSystem_e.swUnitSystem_MMGS);
    }

    // Row-major R (v' = R v + t). CreateTransform stores the rotation
    // TRANSPOSED (solidworks-api.md "stored TRANSPOSED"), so write R^T.
    static IMathTransform Xform(double[] r, double[] t)
    {
        IMathUtility mu = (IMathUtility)sw.GetMathUtility();
        double[] d = new double[16];
        for (int i = 0; i < 3; i++)
            for (int j = 0; j < 3; j++) d[i * 3 + j] = r[j * 3 + i];
        d[9] = M(t[0]); d[10] = M(t[1]); d[11] = M(t[2]); d[12] = 1.0;
        return (IMathTransform)mu.CreateTransform(d);
    }

    static void Comp(string[] f)
    {
        string name = f[1], path = f[2];
        double[] n = Nums(f[3]);
        double[] r = new double[9], t = new double[3];
        Array.Copy(n, r, 9); Array.Copy(n, 9, t, 0, 3);
        int e = 0, w = 0;
        int type = path.ToUpper().EndsWith(".SLDASM") ? (int)swDocumentTypes_e.swDocASSEMBLY
                                                      : (int)swDocumentTypes_e.swDocPART;
        IModelDoc2 pd = (IModelDoc2)sw.OpenDoc6(path, type,
            (int)swOpenDocOptions_e.swOpenDocOptions_Silent, "", ref e, ref w);
        if (pd == null) { Check(name, false, "OpenDoc6 null err " + e); return; }
        sw.ActivateDoc3(asmDoc.GetTitle(), false,
            (int)swRebuildOnActivation_e.swDontRebuildActiveDoc, ref e);
        IComponent2 c = (IComponent2)((IAssemblyDoc)asmDoc).AddComponent5(path,
            (int)swAddComponentConfigOptions_e.swAddComponentConfigOptions_CurrentSelectedConfig,
            "", false, "", 0.0, 0.0, 0.0);
        if (c == null) { Check(name, false, "AddComponent5 null"); return; }
        c.Transform2 = (MathTransform)Xform(r, t);
        if (f.Length > 4 && f[4] == "fix")
        {
            asmDoc.ClearSelection2(true);
            c.Select4(false, null, false);
            ((IAssemblyDoc)asmDoc).FixComponent();
            asmDoc.ClearSelection2(true);
        }
        // Verify: read the transform back and compare with what was written.
        double[] back = (double[])((IMathTransform)c.Transform2).ArrayData;
        double err = Math.Abs(back[9] * 1e3 - t[0]) + Math.Abs(back[10] * 1e3 - t[1]) + Math.Abs(back[11] * 1e3 - t[2]);
        for (int i = 0; i < 3; i++)
            for (int j = 0; j < 3; j++) err += Math.Abs(back[i * 3 + j] - r[j * 3 + i]);
        Check("place " + name, err < 1e-6, string.Format(ci, "t=({0:F2},{1:F2},{2:F2}) readback err {3:E1}",
            t[0], t[1], t[2], err));
        // and close the part window we opened to add it
        if (type == (int)swDocumentTypes_e.swDocPART) sw.CloseDoc(pd.GetTitle());
    }

    static void Interfere()
    {
        asmDoc.EditRebuild3();
        IAssemblyDoc asm = (IAssemblyDoc)asmDoc;
        IInterferenceDetectionMgr idm = asm.InterferenceDetectionManager;
        idm.TreatCoincidenceAsInterference = false;
        idm.TreatSubAssembliesAsComponents = true;
        idm.IncludeMultibodyPartInterferences = false;
        object[] ints = (object[])idm.GetInterferences();
        int n = ints == null ? 0 : ints.Length;
        Console.WriteLine("INTERFERENCES " + n);
        if (ints != null)
            foreach (object o in ints)
            {
                IInterference it = (IInterference)o;
                object[] cs = (object[])it.Components;
                string names = "";
                foreach (object co in cs) names += ((IComponent2)co).Name2 + " ";
                Console.WriteLine(string.Format(ci, "  {0:F1} mm3  {1}", it.Volume * 1e9, names));
            }
        idm.Done();
    }

    static void SaveAsm()
    {
        asmDoc.EditRebuild3();
        asmDoc.ShowNamedView2("*Isometric", -1);
        asmDoc.ViewZoomtofit2();
        IMassProperty mp = (IMassProperty)asmDoc.Extension.CreateMassProperty();
        double[] com = (double[])mp.CenterOfMass;
        Console.WriteLine(string.Format(ci, "  asm volume {0:F1} mm3  centroid ({1:F2}, {2:F2}, {3:F2}) mm",
            mp.Volume * 1e9, com[0] * 1e3, com[1] * 1e3, com[2] * 1e3));
        int e = 0, w = 0;
        bool ok = asmDoc.Extension.SaveAs(asmPath, (int)swSaveAsVersion_e.swSaveAsCurrentVersion,
            (int)swSaveAsOptions_e.swSaveAsOptions_Silent, null, ref e, ref w);
        Check("save " + Path.GetFileName(asmPath), ok, "err " + e + " warn " + w);
    }

    static double PartVolume()
    {
        IMassProperty mp = (IMassProperty)doc.Extension.CreateMassProperty();
        return mp.Volume * 1e9;
    }

    static void Fillet(string[] f)
    {
        double r = double.Parse(f[1], ci);
        string ax = f[2];
        double[] b = Nums(f[3]);
        int want = int.Parse(f[4], ci);
        double[] dv = Nums(f[5]);
        object[] bodies = (object[])((IPartDoc)doc).GetBodies2((int)swBodyType_e.swSolidBody, true);
        var picked = new List<IEdge>();
        foreach (object bo in bodies)
            foreach (object eo in (object[])((IBody2)bo).GetEdges())
            {
                IEdge e = (IEdge)eo;
                ICurve c = (ICurve)e.GetCurve();
                if (c == null || !c.IsLine()) continue;
                double[] p0 = (double[])((IVertex)e.GetStartVertex()).GetPoint();
                double[] p1 = (double[])((IVertex)e.GetEndVertex()).GetPoint();
                double dx = p1[0] - p0[0], dy = p1[1] - p0[1], dz = p1[2] - p0[2];
                double len = Math.Sqrt(dx * dx + dy * dy + dz * dz);
                if (len < 1e-9) continue;
                if (ax != "any")
                {
                    double along = ax == "x" ? dx : ax == "y" ? dy : dz;
                    if (Math.Abs(Math.Abs(along) / len - 1) > 1e-6) continue;
                }
                double mx = (p0[0] + p1[0]) * 500, my = (p0[1] + p1[1]) * 500, mz = (p0[2] + p1[2]) * 500;
                if (mx < b[0] || my < b[1] || mz < b[2] || mx > b[3] || my > b[4] || mz > b[5]) continue;
                picked.Add(e);
            }
        if (picked.Count != want)
        { Check("fillet r" + f[1] + " " + ax + " box " + f[3], false, "selected " + picked.Count + " edges, expected " + want); return; }
        double v0 = PartVolume();
        doc.ClearSelection2(true);
        int nsel = 0;
        foreach (IEdge e in picked) if (((IEntity)e).Select2(true, 1)) nsel++;
        IFeature fil = (IFeature)doc.FeatureManager.FeatureFillet3(
            (int)swFeatureFilletOptions_e.swFeatureFilletUniformRadius, M(r), 0.0, 0.0,
            (int)swFeatureFilletType_e.swFeatureFilletType_Simple,
            (int)swFilletOverFlowType_e.swFilletOverFlowType_Default,
            (int)swFeatureFilletProfileType_e.swFeatureFilletCircular,
            null, null, null, null, null, null, null);
        doc.ClearSelection2(true);
        doc.EditRebuild3();
        double d = PartVolume() - v0;
        Check("fillet r" + f[1] + " " + ax + " box " + f[3], fil != null && Math.Abs(d - dv[0]) <= dv[1],
            string.Format(ci, "{0} edges selected {1}, dvol {2:F2} vs {3:F2} +- {4:F2} mm3 | {5}",
                picked.Count, nsel, d, dv[0], dv[1], Measure()));
    }

    // filletface|r|nz|z|x0 y0 x1 y1|n|dvol tol[|all]  (S1a): fillet every edge of the
    // OUTER loop (inner loops too with "all") of each planar face with normal (0,0,nz) in
    // the plane z whose centre is inside the XY box; n = faces expected, "max" for only the
    // largest one, "any" for >= 1. A plate's top / bottom face outer loop is its outline.
    static void FilletFace(string[] f)
    {
        double r = double.Parse(f[1], ci), nz = double.Parse(f[2], ci), z = double.Parse(f[3], ci);
        double[] b = Nums(f[4]);
        bool largest = f[5] == "max";  // keep only the face with the largest box (the rib
        bool anyN = f[5] == "any";      // grid splits a belly into cells); "any" = >= 1 face
        int want = largest ? 1 : anyN ? -1 : int.Parse(f[5], ci);
        bool inner = f.Length > 7 && f[7] == "all";  // inner loops too (a rib grid's cells)
        double[] dv = Nums(f[6]);
        var picked = new List<IEdge>();
        var cand = new List<IFace2>();
        int faces = 0;
        object[] bodies = (object[])((IPartDoc)doc).GetBodies2((int)swBodyType_e.swSolidBody, true);
        foreach (object bo in bodies)
            foreach (object fo in (object[])((IBody2)bo).GetFaces())
            {
                IFace2 fc = (IFace2)fo;
                if (!((ISurface)fc.GetSurface()).IsPlane()) continue;
                double[] n = (double[])fc.Normal;
                if (Math.Abs(n[2] - nz) > 1e-6) continue;
                double[] bx = (double[])fc.GetBox();
                if (Math.Abs(bx[2] * 1e3 - z) > 1e-3 || Math.Abs(bx[5] * 1e3 - z) > 1e-3) continue;
                double cx = (bx[0] + bx[3]) * 500, cy = (bx[1] + bx[4]) * 500;
                if (cx < b[0] || cy < b[1] || cx > b[2] || cy > b[3]) continue;
                cand.Add(fc);
            }
        if (largest && cand.Count > 1)
        {
            IFace2 best = null; double ba = -1;
            foreach (IFace2 fc in cand)
            {
                double[] bx = (double[])fc.GetBox();
                double a = (bx[3] - bx[0]) * (bx[4] - bx[1]);
                if (a > ba) { ba = a; best = fc; }
            }
            cand = new List<IFace2> { best };
        }
        foreach (IFace2 fc in cand)
        {
            faces++;
            foreach (object lo in (object[])fc.GetLoops())
            {
                ILoop2 lp = (ILoop2)lo;
                if (!lp.IsOuter() && !inner) continue;
                foreach (object eo in (object[])lp.GetEdges()) picked.Add((IEdge)eo);
            }
        }
        string what = "filletface r" + f[1] + " nz " + f[2] + " z " + f[3];
        if (anyN ? faces < 1 : faces != want) { Check(what, false, "matched " + faces + " faces, expected " + f[5]); return; }
        double v0 = PartVolume();
        doc.ClearSelection2(true);
        int nsel = 0;
        foreach (IEdge e in picked) if (((IEntity)e).Select2(true, 1)) nsel++;
        IFeature fil = (IFeature)doc.FeatureManager.FeatureFillet3(
            (int)swFeatureFilletOptions_e.swFeatureFilletUniformRadius, M(r), 0.0, 0.0,
            (int)swFeatureFilletType_e.swFeatureFilletType_Simple,
            (int)swFilletOverFlowType_e.swFilletOverFlowType_Default,
            (int)swFeatureFilletProfileType_e.swFeatureFilletCircular,
            null, null, null, null, null, null, null);
        doc.ClearSelection2(true);
        doc.EditRebuild3();
        double d = PartVolume() - v0;
        Check(what, fil != null && Math.Abs(d - dv[0]) <= dv[1],
            string.Format(ci, "{0} faces, {1} edges selected {2}, dvol {3:F2} vs {4:F2} +- {5:F2} mm3 | {6}",
                faces, picked.Count, nsel, d, dv[0], dv[1], Measure()));
    }

    static void Loop(ISketchManager sm, string spec)
    {
        double[] v = Nums(spec.Substring(2));
        if (spec[0] == 'c') { sm.CreateCircleByRadius(0, 0, 0, M(v[0])); return; }
        int n = v.Length;
        for (int k = 0; k < n; k++)
        {
            double a0 = 2 * Math.PI * k / n, a1 = 2 * Math.PI * (k + 1) / n;
            double r0 = v[k], r1 = v[(k + 1) % n];
            sm.CreateLine(M(r0 * Math.Cos(a0)), M(r0 * Math.Sin(a0)), 0, M(r1 * Math.Cos(a1)), M(r1 * Math.Sin(a1)), 0);
        }
    }

    static void Ring(string[] f)
    {
        double[] z = Nums(f[1]);
        if (!Sketch("front")) return;
        ISketchManager sm = doc.SketchManager;
        sm.AddToDB = true;
        Loop(sm, f[2]);
        if (f[3] != "-") Loop(sm, f[3]);
        CloseSketch();
        bool cut = f[4] == "cut";
        string tag = (f[2][0] == 'p' ? "poly" : f[2]) + " / " + (f[3][0] == 'p' ? "poly" : f[3]);
        After("ring z " + f[1] + " " + tag + (cut ? " cut" : ""), Extrude(z[0], z[1], cut, false));
    }

    static void Stl(string path, string outPath)
    {
        int e = 0, w = 0;
        IModelDoc2 d = (IModelDoc2)sw.OpenDoc6(path, (int)swDocumentTypes_e.swDocPART,
            (int)swOpenDocOptions_e.swOpenDocOptions_Silent, "", ref e, ref w);
        if (d == null) { Check("stl open " + Path.GetFileName(path), false, "err " + e); return; }
        // STL export writes the ACTIVE document, not the one SaveAs is called on (measured
        // 2026-10-30: a mount's STL came out as the last-active reflex envelope)
        d.Visible = true;
        sw.ActivateDoc3(d.GetTitle(), false, (int)swRebuildOnActivation_e.swDontRebuildActiveDoc, ref e);
        sw.SetUserPreferenceIntegerValue((int)swUserPreferenceIntegerValue_e.swExportStlUnits, (int)swLengthUnit_e.swMM);
        sw.SetUserPreferenceIntegerValue((int)swUserPreferenceIntegerValue_e.swSTLQuality, (int)swSTLQuality_e.swSTLQuality_Fine);
        sw.SetUserPreferenceToggle((int)swUserPreferenceToggle_e.swSTLBinaryFormat, true);
        sw.SetUserPreferenceToggle((int)swUserPreferenceToggle_e.swSTLDontTranslateToPositive, true);
        IMassProperty mp = (IMassProperty)d.Extension.CreateMassProperty();
        double vol = mp.Volume * 1e9;
        bool ok = d.Extension.SaveAs(outPath, (int)swSaveAsVersion_e.swSaveAsCurrentVersion,
            (int)swSaveAsOptions_e.swSaveAsOptions_Silent | (int)swSaveAsOptions_e.swSaveAsOptions_Copy, null, ref e, ref w);
        bool exists = File.Exists(outPath);
        Check("stl " + Path.GetFileName(outPath), ok && exists,
            string.Format(ci, "part vol {0:F1} mm3, {1} bytes, err {2}", vol, exists ? new FileInfo(outPath).Length : 0, e));
        sw.CloseDoc(d.GetTitle());
    }

    static void RotBody(string[] f)
    {
        double[] p = Nums(f[1]);
        if (f[2] != "y") { Check("rotbody axis " + f[2], false, "only y is implemented"); return; }
        double rad = double.Parse(f[3], ci) * Math.PI / 180.0;
        doc.ClearSelection2(true);
        ISelectionMgr smgr = (ISelectionMgr)doc.SelectionManager;
        object[] bodies = (object[])((IPartDoc)doc).GetBodies2((int)swBodyType_e.swSolidBody, true);
        foreach (object o in bodies)
        {
            SelectData sd = (SelectData)smgr.CreateSelectData();
            sd.Mark = 1;
            ((IBody2)o).Select2(true, sd);
        }
        IFeature feat = (IFeature)doc.FeatureManager.InsertMoveCopyBody2(0, 0, 0, 0,
            M(p[0]), M(p[1]), M(p[2]), 0, rad, 0, false, 1);
        doc.ClearSelection2(true);
        After("rotbody about y through (" + f[1] + ") by " + f[3] + " deg", feat);
    }

    static void CloseByPath(string path)
    {
        IModelDoc2 d = (IModelDoc2)sw.GetOpenDocumentByName(path);
        if (d != null) sw.CloseDoc(d.GetTitle());
        Check("close " + Path.GetFileName(path), d != null, d == null ? "was not open" : "");
    }

    // SaveBMP only writes when the document window is visible and active
    // (found 2026-10-30; it returns True and writes nothing otherwise).
    static void Shot(string path, string prefix)
    {
        int e = 0, w = 0;
        int type = path.ToUpper().EndsWith(".SLDASM") ? (int)swDocumentTypes_e.swDocASSEMBLY
                                                      : (int)swDocumentTypes_e.swDocPART;
        IModelDoc2 d = (IModelDoc2)sw.OpenDoc6(path, type,
            (int)swOpenDocOptions_e.swOpenDocOptions_Silent, "", ref e, ref w);
        if (d == null) { Check("shot open", false, "err " + e); return; }
        d.Visible = true;
        sw.ActivateDoc3(d.GetTitle(), false, (int)swRebuildOnActivation_e.swDontRebuildActiveDoc, ref e);
        string[] views = { "*Isometric", "*Top", "*Front", "*Right", "*Trimetric" };
        string[] tags = { "iso", "top", "front", "right", "tri" };
        int okc = 0;
        for (int i = 0; i < views.Length; i++)
        {
            d.ShowNamedView2(views[i], -1);
            d.ViewZoomtofit2();
            d.GraphicsRedraw2();
            string p = prefix + "_" + tags[i] + ".bmp";
            if (d.SaveBMP(p, 1400, 1000) && File.Exists(p)) okc++;
        }
        Check("shots " + Path.GetFileName(prefix), okc == views.Length, okc + " of " + views.Length);
    }
}
