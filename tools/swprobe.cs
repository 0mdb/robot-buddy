// swprobe — attach to the running SOLIDWORKS and report what it sees.
//
//   swprobe.exe                 revision + open documents
//   swprobe.exe refs <file>     every document <file> references (no need to open it)
//
// Built and run by tools/sw.py. C# 5 (the in-box csc.exe); early binding so a
// misremembered API name is a compile error, not a silent Nothing. Never starts
// SOLIDWORKS: an instance made by CreateObject never registers in the ROT.
using System;
using System.Runtime.InteropServices;
using SolidWorks.Interop.sldworks;

class SwProbe
{
    static int Main(string[] args)
    {
        // Part names here are not ASCII (Sensorgehäuse...); the OEM codepage mangles them.
        Console.OutputEncoding = System.Text.Encoding.UTF8;
        try
        {
            ISldWorks sw;
            try
            {
                sw = (ISldWorks)Marshal.GetActiveObject("SldWorks.Application");
            }
            catch (COMException)
            {
                Console.WriteLine("PROBE FAILED: SOLIDWORKS is not running -- start it by hand");
                return 2;
            }
            Console.WriteLine("revision " + sw.RevisionNumber());

            if (args.Length == 2 && args[0] == "refs")
            {
                object deps = sw.GetDocumentDependencies2(args[1], true, true, false);
                string[] pairs = deps as string[];
                if (pairs == null)
                {
                    Console.WriteLine("PROBE FAILED: no dependencies returned for " + args[1]);
                    return 1;
                }
                // Flat array of (name, path) pairs.
                for (int i = 0; i + 1 < pairs.Length; i += 2)
                    Console.WriteLine("ref " + pairs[i + 1]);
                Console.WriteLine("refs " + pairs.Length / 2);
            }
            else
            {
                object[] docs = sw.GetDocuments() as object[];
                int n = docs == null ? 0 : docs.Length;
                for (int i = 0; i < n; i++)
                {
                    IModelDoc2 d = (IModelDoc2)docs[i];
                    Console.WriteLine("open " + d.GetType() + " " + d.GetPathName());
                }
                Console.WriteLine("open documents " + n);
            }
            Console.WriteLine("PROBE OK");
            return 0;
        }
        catch (Exception e)
        {
            Console.WriteLine("PROBE FAILED: " + e.GetType().Name + ": " + e.Message);
            return 1;
        }
    }
}
