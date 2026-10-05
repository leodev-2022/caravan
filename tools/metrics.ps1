#Requires -RunAsAdministrator
<#
  Caravan node metrics for Windows — a tiny HttpListener (mesh-only).
  Serves GET /metrics -> {"uptime","cpu","mem","mem_total_mb","mem_used_mb"}.
  Run as SYSTEM (a service / scheduled task) so binding needs no URL ACL.

  Uses fast Win32 APIs (GlobalMemoryStatusEx / GetSystemTimes / GetTickCount64)
  instead of WMI/CIM: on some hosts a single CIM query takes ~2s, which blows
  past the portal's metrics timeout.
#>
[CmdletBinding()]
param(
    [int]$Port = 9101,
    [string]$BindHost = ''   # empty => resolve the node's mesh IP at start
)
$ErrorActionPreference = 'Stop'

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class CaravanSys {
    [StructLayout(LayoutKind.Sequential)]
    private struct MEMORYSTATUSEX {
        public uint dwLength;
        public uint dwMemoryLoad;
        public ulong ullTotalPhys;
        public ulong ullAvailPhys;
        public ulong ullTotalPageFile;
        public ulong ullAvailPageFile;
        public ulong ullTotalVirtual;
        public ulong ullAvailVirtual;
        public ulong ullAvailExtendedVirtual;
    }
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GlobalMemoryStatusEx(ref MEMORYSTATUSEX lpBuffer);
    [DllImport("kernel32.dll")]
    private static extern ulong GetTickCount64();
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetSystemTimes(out long idleTime, out long kernelTime, out long userTime);

    public static long UptimeSeconds() { return (long)(GetTickCount64() / 1000UL); }

    public static void Memory(out long totalMb, out long usedMb) {
        MEMORYSTATUSEX m = new MEMORYSTATUSEX();
        m.dwLength = (uint)Marshal.SizeOf(m);
        GlobalMemoryStatusEx(ref m);
        totalMb = (long)(m.ullTotalPhys / 1024UL / 1024UL);
        usedMb = (long)((m.ullTotalPhys - m.ullAvailPhys) / 1024UL / 1024UL);
    }

    public static void CpuTimes(out long idle, out long kernel, out long user) {
        GetSystemTimes(out idle, out kernel, out user);
    }
}
'@

$script:prev = $null

function Get-PkgVersion($segs) {
    $roots = @('C:\caravan\npm\node_modules')
    $roots += (Get-ChildItem 'C:\Users\*\AppData\Roaming\npm\node_modules' -Directory -ErrorAction SilentlyContinue | ForEach-Object FullName)
    foreach ($r in $roots) {
        $pj = Join-Path $r (($segs + 'package.json') -join '\')
        if (Test-Path $pj) { try { return (Get-Content $pj -Raw | ConvertFrom-Json).version } catch {} }
    }
    return $null
}
$script:engVer = @{
    codenomad = (Get-PkgVersion @('@neuralnomads', 'codenomad'))
    opencode  = (Get-PkgVersion @('@opencode', 'cli'))
}

function Get-CaravanMetrics {
    $idle = [long]0; $kernel = [long]0; $user = [long]0
    [CaravanSys]::CpuTimes([ref]$idle, [ref]$kernel, [ref]$user)
    $cpu = 0.0
    if ($script:prev) {
        $dIdle = $idle - $script:prev.idle
        $dKernel = $kernel - $script:prev.kernel
        $dUser = $user - $script:prev.user
        $dTotal = $dKernel + $dUser
        if ($dTotal -gt 0) { $cpu = [math]::Round(100.0 * ($dTotal - $dIdle) / $dTotal, 1) }
    }
    $script:prev = @{ idle = $idle; kernel = $kernel; user = $user }

    $totalMb = [long]0; $usedMb = [long]0
    [CaravanSys]::Memory([ref]$totalMb, [ref]$usedMb)
    $memPct = if ($totalMb -gt 0) { [math]::Round(100.0 * $usedMb / $totalMb, 1) } else { 0.0 }
    return [ordered]@{
        uptime       = [int][CaravanSys]::UptimeSeconds()
        cpu          = $cpu
        mem          = $memPct
        mem_total_mb = [int]$totalMb
        mem_used_mb  = [int]$usedMb
        engine_versions = $script:engVer
    }
}

# No explicit bind host: resolve the node's *current* mesh IPv4 address at start
# (it can change when the node re-joins), waiting for Tailscale to come up. Never
# fall back to a public interface — loopback if the mesh is not up yet.
if (-not $BindHost) {
    $candidates = @()
    if ($env:ProgramFiles) { $candidates += (Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe') }
    if (${env:ProgramFiles(x86)}) { $candidates += (Join-Path ${env:ProgramFiles(x86)} 'Tailscale\tailscale.exe') }
    $tsExe = ($candidates | Where-Object { Test-Path $_ } | Select-Object -First 1)
    if (-not $tsExe) { $tsExe = 'tailscale' }
    $deadline = (Get-Date).AddMinutes(10)
    while (-not $BindHost) {
        try { $BindHost = [string]((& $tsExe ip -4 2>$null | Select-Object -First 1)).Trim() } catch { $BindHost = '' }
        if ($BindHost) { break }
        if ((Get-Date) -gt $deadline) { break }
        Write-Host '[caravan] waiting for the mesh IP...'
        Start-Sleep -Seconds 5
    }
    if (-not $BindHost) { $BindHost = '127.0.0.1' }
}

# If bound to a specific (mesh) address, wait for it to appear first: this task
# starts at boot, but the Tailscale interface (and its mesh IP) can come up a
# little later — otherwise HttpListener.Start() throws and the node shows
# offline on the hub until the next retry (or an interactive logon).
if ($BindHost -and $BindHost -notin @('0.0.0.0', '::', '*', '+')) {
    $deadline = (Get-Date).AddMinutes(10)
    while (-not (Get-NetIPAddress -IPAddress $BindHost -ErrorAction SilentlyContinue)) {
        if ((Get-Date) -gt $deadline) { throw "bind host $BindHost did not appear within 10m" }
        Write-Host "[caravan] waiting for $BindHost to appear..."
        Start-Sleep -Seconds 5
    }
}

$listener = [System.Net.HttpListener]::new()
$listener.Prefixes.Add("http://${BindHost}:${Port}/")
$listener.Start()
Write-Host "[caravan] metrics on http://${BindHost}:${Port}/metrics"

while ($listener.IsListening) {
    $ctx = $listener.GetContext()
    try {
        $body = (Get-CaravanMetrics | ConvertTo-Json -Compress)
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
        $ctx.Response.ContentType = 'application/json'
        $ctx.Response.ContentLength64 = $bytes.Length
        $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    } catch {
        $ctx.Response.StatusCode = 500
    } finally {
        $ctx.Response.Close()
    }
}
