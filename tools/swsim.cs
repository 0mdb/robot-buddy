// swsim.exe <manifest> -- SolidWorks Simulation static studies for robot-buddy.
//
// Ported from fpv250 design/swsim.cs (docs/simulation.md there); buddy method in
// docs/cad/07_materials_fasteners_fea.md §3. Differences from fpv250: opens a NATIVE
// part (no STEP import), selects faces by position as well as shape, applies remote
// loads (a force/moment at a point, coupled to faces), and reports max von Mises,
// per-region hot spots, displacement on chosen faces, and the reaction sum.
// C# 5, [STAThread], SolidWorks started by hand, one COM client. API lengths: METRES.
//
// Manifest (whitespace separated, # comments; mm, N, N*m, Pa):
//   part     <path.SLDPRT>
//   out      <dir>
//   material <E> <nu> <rho> <strength> <label>          the (single) body
//   fix      <sel>                                      add faces to the fixture
//   load     <id> <sel>                                 a force on faces (total, global axes)
//   remote   <id> <x> <y> <z> <sel>                     a remote load at a point, coupled to faces
//                                                       (repeat the id to add faces to the same load)
//   disp     <label> <sel>                              report max |u| on these faces
//   probe    <label> <x0> <y0> <z0> <x1> <y1> <z1>      report max VON on faces meeting this box
//   mesh     <size> <tol>
//   case     <name> <id>:fx,fy,fz[,mx,my,mz] ...        loads not listed carry ~zero
//   discard_open                                        GENERATED parts only: quit an open copy first
// <sel>: cyl <ax> <ay> <az> <r> <tol> [box x0 y0 z0 x1 y1 z1]      cylinders || a, radius r
//        plane <nx> <ny> <nz> <d> [box ...]                        planes || n at n.p = d
// The box tests the face's bounding-box CENTRE. Ends with "SIM OK" or "SIM FAILED".
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;
using SolidWorks.Interop.cosworks;

static class SwSim
{
    static readonly CultureInfo ci = CultureInfo.InvariantCulture;
    static double D(string s) { return double.Parse(s, ci); }
    static void Log(string fmt, params object[] a) { Console.WriteLine(string.Format(ci, fmt, a)); Console.Out.Flush(); }
    static double Dot(double[] a, double[] b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
    static double[] Unit(double[] a) { double n = Math.Sqrt(Dot(a, a)); return new[] { a[0] / n, a[1] / n, a[2] / n }; }

    // Does face f match the selector starting at t[i]?
    static bool Match(IFace2 f, string[] t, int i)
    {
        ISurface s = (ISurface)f.GetSurface();
        int boxAt;
        if (t[i] == "cyl")
        {
            if (!s.IsCylinder()) return false;
            double[] cp = (double[])s.CylinderParams;   // origin xyz, axis xyz, radius (m)
            double[] ax = Unit(new[] { D(t[i + 1]), D(t[i + 2]), D(t[i + 3]) });
            if (Math.Abs(Math.Abs(Dot(ax, new[] { cp[3], cp[4], cp[5] })) - 1) > 1e-6) return false;
            if (Math.Abs(cp[6] * 1000 - D(t[i + 4])) > D(t[i + 5])) return false;
            boxAt = i + 6;
        }
        else if (t[i] == "plane")
        {
            if (!s.IsPlane()) return false;
            double[] pp = (double[])s.PlaneParams;      // normal xyz, root xyz (m)
            double[] n = Unit(new[] { D(t[i + 1]), D(t[i + 2]), D(t[i + 3]) });
            double c = Dot(n, new[] { pp[0], pp[1], pp[2] });
            if (Math.Abs(Math.Abs(c) - 1) > 1e-6) return false;
            if (Math.Abs(Dot(n, new[] { pp[3], pp[4], pp[5] }) * 1000 - D(t[i + 4])) > 1e-3) return false;
            boxAt = i + 5;
        }
        else throw new Exception("unknown selector " + t[i]);
        if (t.Length > boxAt && t[boxAt] == "box")
        {
            double[] b = (double[])f.GetBox();
            double cx = (b[0] + b[3]) * 500, cy = (b[1] + b[4]) * 500, cz = (b[2] + b[5]) * 500;
            if (cx < D(t[boxAt + 1]) || cy < D(t[boxAt + 2]) || cz < D(t[boxAt + 3]) ||
                cx > D(t[boxAt + 4]) || cy > D(t[boxAt + 5]) || cz > D(t[boxAt + 6])) return false;
        }
        return true;
    }

    static object[] Select(List<IFace2> faces, string[] t, int i, string what)
    {
        var r = new List<object>();
        foreach (IFace2 f in faces) if (Match(f, t, i)) r.Add(f);
        Log("{0}: {1} faces", what, r.Count);
        if (r.Count == 0) throw new Exception(what + " selected no face");
        return r.ToArray();
    }

    static double MaxPair(object[] arr)   // [node, value, node, value, ...] -> max value
    {
        double m = double.NegativeInfinity;
        if (arr == null) return double.NaN;
        for (int k = 1; k < arr.Length; k += 2) m = Math.Max(m, Convert.ToDouble(arr[k], ci));
        return m;
    }

    [STAThread]
    static int Main(string[] args)
    {
        try { int r = Run(args); Log(r == 0 ? "SIM OK" : "SIM FAILED"); return r; }
        catch (Exception ex) { Console.WriteLine("FATAL " + ex); Console.WriteLine("SIM FAILED"); return 2; }
    }

    static int Run(string[] args)
    {
        var lines = new List<string[]>();
        foreach (string raw in File.ReadAllLines(args[0]))
        {
            string l = raw.Split('#')[0].Trim();
            if (l.Length > 0) lines.Add(l.Split(new[] { ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries));
        }
        string partPath = null, outDir = null; string[] mat = null;
        double meshSize = 2.0, meshTol = 0.1;
        bool discardOpen = false;   // only for GENERATED parts: throw away an open copy first
        var fixes = new List<string[]>(); var loads = new List<string[]>(); var remotes = new List<string[]>();
        var disps = new List<string[]>(); var probes = new List<string[]>(); var cases = new List<string[]>();
        foreach (string[] t in lines)
            switch (t[0])
            {
                case "part": partPath = t[1]; break;
                case "out": outDir = t[1]; break;
                case "material": mat = t; break;
                case "fix": fixes.Add(t); break;
                case "load": loads.Add(t); break;
                case "remote": remotes.Add(t); break;
                case "disp": disps.Add(t); break;
                case "probe": probes.Add(t); break;
                case "mesh": meshSize = D(t[1]); meshTol = D(t[2]); break;
                case "case": cases.Add(t); break;
                case "discard_open": discardOpen = true; break;
                default: throw new Exception("unknown manifest line " + t[0]);
            }
        Directory.CreateDirectory(outDir);
        ISldWorks sw = null;
        for (int i = 0; i < 30 && sw == null; i++)
        {
            try { sw = (ISldWorks)Marshal.GetActiveObject("SldWorks.Application"); }
            catch (COMException) { System.Threading.Thread.Sleep(1000); }
        }
        if (sw == null) throw new Exception("no SolidWorks in the ROT -- start SLDWORKS.exe by hand");

        int e = 0, w = 0;
        IModelDoc2 already = (IModelDoc2)sw.GetOpenDocumentByName(partPath);
        if (already != null && discardOpen) { Log("discarding the open copy of {0}", Path.GetFileName(partPath)); sw.QuitDoc(already.GetTitle()); already = null; }
        IModelDoc2 doc = (IModelDoc2)sw.OpenDoc6(partPath, (int)swDocumentTypes_e.swDocPART,
            (int)swOpenDocOptions_e.swOpenDocOptions_Silent, "", ref e, ref w);
        if (doc == null) throw new Exception("OpenDoc6 null err=" + e);
        try { return Study(sw, doc, partPath, outDir, mat, meshSize, meshTol, fixes, loads, remotes, disps, probes, cases); }
        finally { if (already == null) sw.QuitDoc(doc.GetTitle()); }   // close WITHOUT saving
    }

    static int Study(ISldWorks sw, IModelDoc2 doc, string partPath, string outDir, string[] mat,
                     double meshSize, double meshTol, List<string[]> fixes, List<string[]> loads,
                     List<string[]> remotes, List<string[]> disps, List<string[]> probes, List<string[]> cases)
    {
        int e = 0;
        doc.Visible = true;
        sw.ActivateDoc3(doc.GetTitle(), false, (int)swRebuildOnActivation_e.swDontRebuildActiveDoc, ref e);
        Array bodies = ((IPartDoc)doc).GetBodies2((int)swBodyType_e.swSolidBody, true) as Array;
        if (bodies == null || bodies.Length != 1) throw new Exception("want one solid body");
        var faces = new List<IFace2>();
        foreach (object f in (Array)((IBody2)bodies.GetValue(0)).GetFaces()) faces.Add((IFace2)f);
        Log("part {0}: {1} faces", Path.GetFileName(partPath), faces.Count);

        var fixFaces = new List<object>();
        foreach (string[] t in fixes) fixFaces.AddRange(Select(faces, t, 1, "fix " + t[1]));
        var loadFaces = new Dictionary<string, object[]>();
        foreach (string[] t in loads) loadFaces[t[1]] = Select(faces, t, 2, "load " + t[1]);
        // repeated remote ids pool their faces into ONE remote load at the first line's point
        var remoteFaces = new Dictionary<string, List<object>>();
        var remoteAt = new Dictionary<string, string[]>();
        foreach (string[] t in remotes)
        {
            if (!remoteFaces.ContainsKey(t[1])) { remoteFaces[t[1]] = new List<object>(); remoteAt[t[1]] = t; }
            remoteFaces[t[1]].AddRange(Select(faces, t, 5, "remote " + t[1]));
        }
        var dispFaces = new Dictionary<string, object[]>();
        foreach (string[] t in disps) dispFaces[t[1]] = Select(faces, t, 2, "disp " + t[1]);
        var probeFaces = new Dictionary<string, object[]>();
        foreach (string[] t in probes)
        {
            var pf = new List<object>();
            foreach (IFace2 f in faces)
            {
                double[] b = (double[])f.GetBox();
                if (b[0] * 1000 <= D(t[5]) && b[3] * 1000 >= D(t[2]) && b[1] * 1000 <= D(t[6]) &&
                    b[4] * 1000 >= D(t[3]) && b[2] * 1000 <= D(t[7]) && b[5] * 1000 >= D(t[4])) pf.Add(f);
            }
            Log("probe {0}: {1} faces", t[1], pf.Count);
            if (pf.Count > 0) probeFaces[t[1]] = pf.ToArray();
        }

        CwAddincallback cb = (CwAddincallback)sw.GetAddInObject("SldWorks.Simulation");
        if (cb == null)
        {
            string ex = sw.GetExecutablePath();
            if (ex.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) ex = Path.GetDirectoryName(ex);
            Log("LoadAddIn Simulation = {0}", sw.LoadAddIn(Path.Combine(ex, @"Simulation\cosworks.dll")));
            cb = (CwAddincallback)sw.GetAddInObject("SldWorks.Simulation");
        }
        if (cb == null) throw new Exception("Simulation add-in not loaded");
        CWModelDoc cdoc = cb.CosmosWorks.ActiveDoc;
        CWStudy study = cdoc.StudyManager.CreateNewStudy3("buddy-" + DateTime.Now.ToString("HHmmss"), 0, 0, out e);
        if (study == null) throw new Exception("CreateNewStudy3 err=" + e);

        CWSolidComponent comp = study.SolidManager.GetComponentAt(0, out e);
        CWSolidBody sb = comp.GetSolidBodyAt(0, out e);
        CWMaterial m = sb.GetDefaultMaterial();
        m.MaterialUnits = 0;
        m.MaterialName = "buddy " + mat[5];
        m.SetPropertyByName("EX", D(mat[1]), 0);
        m.SetPropertyByName("NUXY", D(mat[2]), 0);
        m.SetPropertyByName("DENS", D(mat[3]), 0);
        m.SetPropertyByName("SIGXT", D(mat[4]), 0);
        m.SetPropertyByName("SIGYLD", D(mat[4]), 0);
        Log("material {0}: {1}", mat[5], sb.SetSolidBodyMaterial(m));

        CWLoadsAndRestraintsManager lr = study.LoadsAndRestraintsManager;
        if (fixFaces.Count == 0) throw new Exception("no fixture");
        lr.AddRestraint(0, fixFaces.ToArray(), null, out e);
        Log("restraint on {0} faces err={1}", fixFaces.Count, e);
        IFeature front = (IFeature)((IPartDoc)doc).FeatureByName("Front Plane");
        var forces = new Dictionary<string, CWForce>();
        foreach (var kv in loadFaces)
        {
            CWForce fo = lr.AddForce2(0, 0, kv.Value, front, out e);
            if (fo == null) throw new Exception("AddForce2 " + kv.Key + " err=" + e);
            forces[kv.Key] = fo;
        }
        var rloads = new Dictionary<string, CWRemoteLoad>();
        foreach (string[] t in remoteAt.Values)
        {
            CWRemoteLoad rl = lr.AddRemoteLoad(0, remoteFaces[t[1]].ToArray(), 0, D(t[2]), D(t[3]), D(t[4]), out e);
            if (rl == null) throw new Exception("AddRemoteLoad " + t[1] + " err=" + e);
            rloads[t[1]] = rl;
            double x, y, z; rl.GetLocationValues(out x, out y, out z);
            Log("remote {0} at ({1}, {2}, {3}) unit {4}", t[1], x, y, z, rl.LocationUnit);
        }

        e = study.CreateMesh(0, meshSize, meshTol);   // units 0 = mm (as fpv250 passes it)
        Log("mesh {0} mm: err={1} nodes={2} elements={3}", meshSize, e, study.Mesh.NodeCount, study.Mesh.ElementCount);
        if (e != 0 || study.Mesh.IsMeshFailed2) throw new Exception("mesh failed");

        var report = new StringBuilder("case,item,value,unit\n");
        foreach (string[] t in cases)
        {
            var val = new Dictionary<string, double[]>();
            for (int k = 2; k < t.Length; ++k)
            {
                string[] kv = t[k].Split(':'); string[] c = kv[1].Split(',');
                double[] v = new double[6];
                for (int j = 0; j < c.Length; j++) v[j] = D(c[j]);
                val[kv[0]] = v;
            }
            int fe = 0;
            foreach (var kv in forces)
            {
                double[] v; if (!val.TryGetValue(kv.Key, out v)) v = new[] { 0.0, 0.0, 1e-6 };
                kv.Value.ForceBeginEdit();
                kv.Value.Unit = 0;
                // AddForce2(.., 0, ..) applies the value to EACH face (reaction sum = n x value,
                // measured 2026-10-30), so split the case's total evenly across the faces
                int nf = loadFaces[kv.Key].Length;
                kv.Value.SetForceComponentValues(1, 1, 1, v[0] / nf, v[1] / nf, v[2] / nf);
                fe |= kv.Value.ForceEndEdit();
            }
            foreach (var kv in rloads)
            {
                double[] v; if (!val.TryGetValue(kv.Key, out v)) v = new[] { 0.0, 0.0, 1e-6, 0, 0, 0 };
                kv.Value.RemoteLoadBeginEdit();
                kv.Value.SetForceOrTranslationValues2(true, true, v[0], true, v[1], true, v[2]);
                kv.Value.SetMomentOrRotationValues2(true, true, v[3], true, v[4], true, v[5]);
                fe |= kv.Value.RemoteLoadEndEdit();
            }
            int re = study.RunAnalysis();
            Log("case {0}: edit err={1} run err={2}", t[1], fe, re);
            if (fe != 0 || re != 0) throw new Exception("case " + t[1] + " failed");
            CWResults res = study.Results;
            if (res == null) throw new Exception("case " + t[1] + ": no results");

            object[] smm = (object[])res.GetMinMaxStress(9, 0, 0, null, 0, out e);
            double vmax = Convert.ToDouble(smm[3], ci);
            Log("  max VON {0:F3} MPa (node {1})", vmax / 1e6, smm[2]);
            report.AppendFormat(ci, "{0},max_von,{1:F4},MPa\n", t[1], vmax / 1e6);
            object[] dmm = (object[])res.GetMinMaxDisplacement(3, 0, null, 0, out e);
            double umax = Convert.ToDouble(dmm[3], ci);
            Log("  max URES {0:F4} mm", umax);
            report.AppendFormat(ci, "{0},max_ures,{1:F5},mm\n", t[1], umax);
            object[] rf = (object[])res.GetReactionForcesAndMoments(0, null, 0, out e);
            // per node: node, FX, FY, FZ, F, MX, MY, MZ, M  (stride 9, measured 2026-10-30)
            if (rf != null && rf.Length % 9 == 0)
            {
                double rx = 0, ry = 0, rz = 0;
                for (int k = 0; k < rf.Length; k += 9)
                { rx += Convert.ToDouble(rf[k + 1], ci); ry += Convert.ToDouble(rf[k + 2], ci); rz += Convert.ToDouble(rf[k + 3], ci); }
                Log("  reaction sum ({0:F2}, {1:F2}, {2:F2}) N over {3} nodes", rx, ry, rz, rf.Length / 9);
                report.AppendFormat(ci, "{0},reaction,{1:F3} {2:F3} {3:F3},N\n", t[1], rx, ry, rz);
            }
            else Log("  reaction: unexpected array length {0}", rf == null ? -1 : rf.Length);
            foreach (var kv in probeFaces)
            {
                double pm = double.NegativeInfinity;
                for (int b0 = 0; b0 < kv.Value.Length; b0 += 10)
                {
                    object[] part = new object[Math.Min(10, kv.Value.Length - b0)];
                    Array.Copy(kv.Value, b0, part, 0, part.Length);
                    pm = Math.Max(pm, MaxPair((object[])res.GetStressForEntities(9, 0, null, part, 0, out e)));
                }
                Log("  probe {0}: max VON {1:F3} MPa", kv.Key, pm / 1e6);
                report.AppendFormat(ci, "{0},probe_{1},{2:F4},MPa\n", t[1], kv.Key, pm / 1e6);
            }
            foreach (var kv in dispFaces)
            {
                // components: 0 UX, 1 UY, 2 UZ, 3 URES; units 0 = mm (swsLinearUnit_e)
                string[] cn = { "ux", "uy", "uz", "ures" };
                var sbd = new StringBuilder();
                for (int c = 0; c < 4; c++)
                {
                    object[] d = (object[])res.GetDisplacementForEntities(c, 0, null, kv.Value, 0, out e);
                    double lo = double.PositiveInfinity, hi = double.NegativeInfinity;
                    for (int k = 1; d != null && k < d.Length; k += 2)
                    { double v = Convert.ToDouble(d[k], ci); lo = Math.Min(lo, v); hi = Math.Max(hi, v); }
                    sbd.AppendFormat(ci, " {0} [{1:F4}, {2:F4}]", cn[c], lo, hi);
                    report.AppendFormat(ci, "{0},disp_{1}_{2},{3:F5} {4:F5},mm\n", t[1], kv.Key, cn[c], lo, hi);
                }
                Log("  disp {0} (mm):{1}", kv.Key, sbd.ToString());
            }
        }
        File.WriteAllText(Path.Combine(outDir, "results.csv"), report.ToString());
        return 0;
    }
}
