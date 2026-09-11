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
    [switch]$Yes,
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
if (-not $Yes) {
    $ans = Read-Host 'Continue? [y/N]'
    if ($ans -notmatch '^[yY]') { Write-Host 'aborted'; exit 1 }
}

function Have([string]$c) { $null -ne (Get-Command $c -ErrorAction SilentlyContinue) }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
        [Environment]::GetEnvironmentVariable('Path', 'User')
}

# --- Node.js ---
if (-not (Have node)) {
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'x64' }
    Write-Host '[caravan] resolving latest Node.js LTS'
    $idx = Invoke-RestMethod -Uri 'https://nodejs.org/dist/index.json' -TimeoutSec 30
    $ver = ($idx | Where-Object { $_.lts } | Select-Object -First 1).version
    $msi = Join-Path $env:TEMP "node-$ver-$arch.msi"
    Write-Host "[caravan] downloading Node.js $ver ($arch)"
    Invoke-WebRequest -UseBasicParsing -Uri "https://nodejs.org/dist/$ver/node-$ver-$arch.msi" -OutFile $msi -TimeoutSec 600
    Write-Host '[caravan] installing Node.js (msi)'
    Start-Process msiexec.exe -Wait -ArgumentList "/i `"$msi`" /qn /norestart"
    Remove-Item $msi -Force -ErrorAction SilentlyContinue
    Refresh-Path
}
if (-not (Have node)) { throw 'node not found after install — reopen the shell and retry' }

# --- engine ---
# NB: resolve the npm .cmd shim (not the .ps1) so a batch/scheduled task can run it.
$prefix = (& npm prefix -g | Select-Object -First 1).Trim()
if ($Engine -eq 'opencode') {
    if (-not (Have opencode)) { npm install -g opencode-ai }
    $exe = Join-Path $prefix 'opencode.cmd'
    if (-not (Test-Path $exe)) { $exe = (Get-Command opencode -ErrorAction SilentlyContinue).Source }
    $exeArgs = "web --port $Port --hostname 0.0.0.0"
} else {
    if (-not (Have codenomad)) { npm install -g @neuralnomads/codenomad opencode-ai }
    $exe = Join-Path $prefix 'codenomad.cmd'
    if (-not (Test-Path $exe)) { $exe = (Get-Command codenomad -ErrorAction SilentlyContinue).Source }
    $exeArgs = "--https=false --http=true --host 0.0.0.0 --http-port $Port --dangerously-skip-auth --workspace-root `"$WorkspaceRoot`""
}

# The engine runs as SYSTEM, which does not see the per-user npm dir. Expose it
# machine-wide and point CodeNomad at the direct opencode .exe, so it does not
# use its racy ".cmd" wrapper path (which fails with "unknown PID").
$machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
if (($machinePath -split ';') -notcontains $prefix) {
    [Environment]::SetEnvironmentVariable('Path', ($machinePath.TrimEnd(';') + ';' + $prefix), 'Machine')
}
if ($Engine -eq 'codenomad') {
    $ocExe = Join-Path $prefix 'node_modules\opencode-ai\bin\opencode.exe'
    $cfgDir = Join-Path $env:windir 'system32\config\systemprofile\.config\codenomad'
    New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
    Set-Content -Path (Join-Path $cfgDir 'config.yaml') -Encoding UTF8 -Value "server:`n  opencodeBinary: '$ocExe'`n"
}

# --- Tailscale (mesh) ---
$ts = (Get-Command tailscale -ErrorAction SilentlyContinue).Source
if (-not $ts) { $cand = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'; if (Test-Path $cand) { $ts = $cand } }
if (-not $ts) {
    Write-Host '[caravan] downloading Tailscale'
    $setup = Join-Path $env:TEMP 'tailscale-setup.exe'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://pkgs.tailscale.com/stable/tailscale-setup-latest.exe' -OutFile $setup -TimeoutSec 600
    Write-Host '[caravan] installing Tailscale'
    Start-Process $setup -Wait -ArgumentList '/quiet'
    Remove-Item $setup -Force -ErrorAction SilentlyContinue
    $ts = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
}
if (-not $ts -or -not (Test-Path $ts)) { throw 'tailscale.exe not found after install' }
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
