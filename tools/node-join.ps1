#Requires -RunAsAdministrator
<#
  Caravan node onboarding for Windows (run as Administrator).

  Joins the mesh (Tailscale), installs the engine (CodeNomad or opencode web),
  and registers both the engine and the metrics agent as Scheduled Tasks
  (ONSTART, SYSTEM, highest privileges).

  Example:
    .\node-join.ps1 -Hub https://mesh.example.com -Token hskey-auth-XXXX -Name pc1
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Hub,
    [Parameter(Mandatory = $true)][string]$Token,
    [string]$Name = $env:COMPUTERNAME,
    [ValidateSet('codenomad', 'opencode')][string]$Engine = 'codenomad',
    [int]$Port = 0,
    [string]$WorkspaceRoot = $env:USERPROFILE,
    [int]$MetricsPort = 9101,
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
if ($Port -eq 0) { $Port = if ($Engine -eq 'opencode') { 4096 } else { 9898 } }

Write-Host ''
Write-Warning 'Caravan is early-stage (pre-1.0) software — use at your own risk.'
Write-Host '  * Join a FRESH / throwaway machine — NOT one with critical data.'
Write-Host '  * Installs Node.js, the engine and Tailscale, and registers Scheduled Tasks.'
Write-Host '  * MIT licence: provided "as is", without warranty.'
if ($DryRun) {
    Write-Host "[caravan] dry-run: engine=$Engine name=$Name port=$Port metrics=$MetricsPort hub=$Hub ws=$WorkspaceRoot"
    return
}
$ans = Read-Host 'Continue? [y/N]'
if ($ans -notmatch '^[yY]') { Write-Host 'aborted'; exit 1 }

function Have([string]$c) { $null -ne (Get-Command $c -ErrorAction SilentlyContinue) }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
        [Environment]::GetEnvironmentVariable('Path', 'User')
}

# --- Node.js ---
if (-not (Have node)) {
    Write-Host '[caravan] installing Node.js (winget)'
    winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
    Refresh-Path
}
if (-not (Have node)) { throw 'node not found after install — reopen the shell and retry' }

# --- engine ---
if ($Engine -eq 'opencode') {
    if (-not (Have opencode)) { npm install -g opencode-ai }
    $exe = (Get-Command opencode -ErrorAction SilentlyContinue).Source
    if (-not $exe) { $exe = Join-Path $env:APPDATA 'npm\opencode.cmd' }
    $exeArgs = "web --port $Port --hostname 0.0.0.0"
} else {
    if (-not (Have codenomad)) { npm install -g @neuralnomads/codenomad opencode-ai }
    $exe = (Get-Command codenomad -ErrorAction SilentlyContinue).Source
    if (-not $exe) { $exe = Join-Path $env:APPDATA 'npm\codenomad.cmd' }
    $exeArgs = "--https=false --http=true --host 0.0.0.0 --http-port $Port --dangerously-skip-auth --workspace-root `"$WorkspaceRoot`""
}

# --- Tailscale (mesh) ---
if (-not (Have tailscale)) {
    Write-Host '[caravan] installing Tailscale (winget)'
    winget install --id Tailscale.Tailscale -e --accept-source-agreements --accept-package-agreements
    Refresh-Path
}
$ts = (Get-Command tailscale -ErrorAction SilentlyContinue).Source
if (-not $ts) { $ts = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe' }
Write-Host "[caravan] joining mesh as $Name"
& $ts up "--login-server=$Hub" "--authkey=$Token" "--hostname=$Name" '--accept-dns=false'
Start-Sleep -Seconds 4
$meshIp = (& $ts ip -4 | Select-Object -First 1)

# --- engine as a Scheduled Task (ONSTART, SYSTEM) ---
$dir = Join-Path $env:ProgramData 'caravan'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$cmdPath = Join-Path $dir 'node.cmd'
Set-Content -Path $cmdPath -Encoding ASCII -Value "@echo off`r`n`"$exe`" $exeArgs"
schtasks /Create /TN 'CaravanNode' /TR "`"$cmdPath`"" /SC ONSTART /RU SYSTEM /RL HIGHEST /F | Out-Null
schtasks /Run /TN 'CaravanNode' | Out-Null

# --- metrics agent as a Scheduled Task (bound to the mesh IP) ---
$mPath = Join-Path $dir 'metrics.ps1'
Copy-Item -Force (Join-Path $PSScriptRoot 'metrics.ps1') $mPath
$mCmd = Join-Path $dir 'metrics.cmd'
Set-Content -Path $mCmd -Encoding ASCII -Value "@echo off`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"$mPath`" -BindHost $meshIp -Port $MetricsPort"
schtasks /Create /TN 'CaravanMetrics' /TR "`"$mCmd`"" /SC ONSTART /RU SYSTEM /RL HIGHEST /F | Out-Null
schtasks /Run /TN 'CaravanMetrics' | Out-Null

Write-Host "[caravan] DONE. $Name mesh-ip=$meshIp port=$Port"
Write-Host "[caravan] register on the hub: portal Invite -> Add (name=$Name ip=$meshIp port=$Port)"
Write-Host "[caravan] uninstall: schtasks /Delete /TN CaravanNode /F ; schtasks /Delete /TN CaravanMetrics /F"
