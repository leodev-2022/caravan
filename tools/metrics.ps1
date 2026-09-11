#Requires -RunAsAdministrator
<#
  Caravan node metrics for Windows — a tiny HttpListener (mesh-only).
  Serves GET /metrics -> {"uptime","cpu","mem","mem_total_mb","mem_used_mb"}.
  Run as SYSTEM (a service / scheduled task) so binding needs no URL ACL.
#>
[CmdletBinding()]
param(
    [int]$Port = 9101,
    [string]$BindHost = '0.0.0.0'
)
$ErrorActionPreference = 'Stop'

function Get-CaravanMetrics {
    $os = Get-CimInstance -ClassName Win32_OperatingSystem
    $uptime = [int]((Get-Date) - $os.LastBootUpTime).TotalSeconds
    $cpu = 0.0
    try {
        $avg = (Get-CimInstance -ClassName Win32_Processor |
            Measure-Object -Property LoadPercentage -Average).Average
        if ($null -ne $avg) { $cpu = [math]::Round([double]$avg, 1) }
    } catch { }
    $memTotal = [int]($os.TotalVisibleMemorySize / 1024)
    $memFree = [int]($os.FreePhysicalMemory / 1024)
    $memUsed = $memTotal - $memFree
    $memPct = if ($memTotal -gt 0) { [math]::Round(100.0 * $memUsed / $memTotal, 1) } else { 0.0 }
    return [ordered]@{
        uptime      = $uptime
        cpu         = $cpu
        mem         = $memPct
        mem_total_mb = $memTotal
        mem_used_mb  = $memUsed
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
