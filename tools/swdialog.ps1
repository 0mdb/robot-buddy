# swdialog.ps1 -- find (and optionally answer) modal dialogs that block a SolidWorks
# Simulation run. Called by tools/fea.py while swsim.exe runs (docs/cad/loop BACKLOG T8).
#
#   powershell -File swdialog.ps1 [-Procs star,SLDWORKS] [-Answer]
#
# Prints one line per visible #32770 dialog owned by those processes:
#   DIALOG <hwnd> <process> "<title>" texts=[...] buttons=[...]
# With -Answer, a dialog that is positively identified as a KNOWN prompt is answered
# and reported as ANSWERED <hwnd> <button> <reason>. Unknown dialogs are only reported.
#
# Known prompts (match on text we can read: a dialog's message is often in an Edit
# control that GetWindowText cannot read across processes, so match stable labels):
#   - "Excessive displacements ... Large Displacement?" (title "Simulation", KB link
#     QA00000118617, buttons Yes/No/Cancel) -> No: keep the linear results.
param([string[]]$Procs = @("star", "SLDWORKS"), [switch]$Answer)

Add-Type @"
using System; using System.Runtime.InteropServices; using System.Text;
public class SwDlg {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr p, EnumProc f, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  public static string T(IntPtr h){ var s=new StringBuilder(1024); GetWindowText(h,s,1024); return s.ToString(); }
  public static string C(IntPtr h){ var s=new StringBuilder(256); GetClassName(h,s,256); return s.ToString(); }
}
"@

$pids = @{}
foreach ($p in Get-Process -ErrorAction SilentlyContinue | Where-Object { $Procs -contains $_.ProcessName }) { $pids[[uint32]$p.Id] = $p.ProcessName }
$dialogs = New-Object System.Collections.Generic.List[IntPtr]
[SwDlg]::EnumWindows({ param($h, $l)
    $p = [uint32]0; [SwDlg]::GetWindowThreadProcessId($h, [ref]$p) | Out-Null
    if ($pids.ContainsKey($p) -and [SwDlg]::IsWindowVisible($h) -and [SwDlg]::C($h) -eq "#32770") { $dialogs.Add($h) }
    return $true }, [IntPtr]::Zero) | Out-Null

foreach ($d in $dialogs) {
    $p = [uint32]0; [SwDlg]::GetWindowThreadProcessId($d, [ref]$p) | Out-Null
    $title = [SwDlg]::T($d)
    $texts = New-Object System.Collections.Generic.List[string]
    $buttons = @{}
    [SwDlg]::EnumChildWindows($d, { param($c, $l2)
        $t = [SwDlg]::T($c)
        if ([SwDlg]::C($c) -eq "Button") { if ($t) { $buttons[($t -replace "&", "")] = $c } }
        elseif ($t) { $texts.Add($t) }
        return $true }, [IntPtr]::Zero) | Out-Null
    $all = $texts -join " | "
    "DIALOG $d $($pids[$p]) `"$title`" texts=[$all] buttons=[$($buttons.Keys -join ',')]"
    if (-not $Answer) { continue }
    if ($title -eq "Simulation" -and $all -like "*QA00000118617*" -and $buttons.ContainsKey("No")) {
        [SwDlg]::SendMessage($buttons["No"], 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null   # BM_CLICK
        "ANSWERED $d No excessive-displacement prompt: keep the linear results"
    }
}
