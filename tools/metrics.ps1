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
    [string]$BindHost = '0.0.0.0'
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
