#Requires -RunAsAdministrator
<#
  Caravan node onboarding for Windows (run as Administrator).

  Joins the mesh (Tailscale), installs the engine (CodeNomad or opencode web),
  and registers the engine, the metrics agent and a watchdog as Scheduled Tasks
  (SYSTEM, highest privileges, no execution-time limit, restart-on-failure).
  The watchdog re-starts a service whenever its port stops listening, so the
  node self-heals (Windows' default 72h task limit would otherwise kill it).

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
    [int]$WatchdogMinutes = 5,
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
# The engine pair needs Node >= 22 (@opencode/client calls Promise.withResolvers(),
# only present from Node 22). An older Node silently breaks the engine at runtime.
$nodeMajor = 0
if (Have node) {
    try { $nodeMajor = [int](((node --version) -replace '^v', '') -split '\.')[0] } catch { $nodeMajor = 0 }
}
if ($nodeMajor -lt 22) {
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'x64' }
    if (Have node) {
        Write-Host "[caravan] Node $(node --version) is too old for the engine (needs >= 22) - upgrading"
    }
    else {
        Write-Host '[caravan] resolving latest Node.js LTS'
    }
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
# Install into an ASCII-only prefix. On non-English Windows the user profile
# (e.g. C:\Users\<cyrillic>) is non-ASCII, and Node's spawn / CodeNomad's
# process handling mangle such paths (ENOENT, "spawn ...open .exe") — so we
# install machine-wide under ProgramData instead of the per-user npm dir.
$prefix = Join-Path $env:ProgramData 'caravan\npm'
New-Item -ItemType Directory -Force -Path $prefix | Out-Null
# Pin a COMPATIBLE PAIR: CodeNomad needs an exact opencode version (its
# @opencode/client dependency); opencode v2 ships as @opencode/cli. Never
# "latest to latest" (0.20.1 rejects opencode 1.x).
$CodenomadV = '0.20.1'
$OpencodeV = '2.0.22'
if ($Engine -eq 'opencode') {
    if (-not (Test-Path (Join-Path $prefix 'node_modules\@opencode\cli\package.json'))) {
        npm install -g --prefix $prefix "@opencode/cli@$OpencodeV"
    }
    $exe = Join-Path $prefix 'opencode.cmd'
    $exeArgs = "web --port $Port --hostname 0.0.0.0"
} else {
    if (-not (Test-Path (Join-Path $prefix 'node_modules\@opencode\cli\package.json'))) {
        npm install -g --prefix $prefix "@neuralnomads/codenomad@$CodenomadV" "@opencode/cli@$OpencodeV"
    }
    $exe = Join-Path $prefix 'codenomad.cmd'
    $exeArgs = "--https=false --http=true --host 0.0.0.0 --http-port $Port --dangerously-skip-auth --workspace-root `"$WorkspaceRoot`""
}
if (-not (Test-Path $exe)) { throw "engine shim not found: $exe" }

# The engine runs as SYSTEM, which does not see the per-user npm dir. Expose it
# machine-wide and point CodeNomad at the direct opencode .exe, so it does not
# use its racy ".cmd" wrapper path (which fails with "unknown PID").
$machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
if (($machinePath -split ';') -notcontains $prefix) {
    [Environment]::SetEnvironmentVariable('Path', ($machinePath.TrimEnd(';') + ';' + $prefix), 'Machine')
}
if ($Engine -eq 'codenomad') {
    $ocExe = Join-Path $prefix 'node_modules\@opencode\cli\bin\opencode.exe'
    $cfgDir = Join-Path $env:windir 'system32\config\systemprofile\.config\codenomad'
    New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
    Set-Content -Path (Join-Path $cfgDir 'config.yaml') -Encoding UTF8 -Value "server:`n  opencodeBinary: '$ocExe'`n"

    # CodeNomad identifies/stops its Windows child processes by shelling out to
    # PowerShell + Get-CimInstance Win32_Process, which takes ~1-2s on a busy
    # machine — longer than its default 1s stop-command timeout, so workspaces
    # randomly fail to launch ("spawnSync powershell.exe ETIMEDOUT"). Raise the
    # timeouts until the upstream fix lands.
    # Upstream: https://github.com/NeuralNomadsAI/CodeNomad/issues/753
    $rt = Join-Path $prefix 'node_modules\@neuralnomads\codenomad\dist\workspaces\runtime.js'
    if (Test-Path $rt) {
        $s = [IO.File]::ReadAllText($rt)
        $s = $s.Replace('options.stopCommandTimeoutMs ?? 1000', 'options.stopCommandTimeoutMs ?? 8000')
        $s = $s.Replace('options.gracefulStopTimeoutMs ?? 2000', 'options.gracefulStopTimeoutMs ?? 6000')
        $s = $s.Replace('options.forcedStopTimeoutMs ?? 2000', 'options.forcedStopTimeoutMs ?? 6000')
        [IO.File]::WriteAllText($rt, $s)
    }
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
& $ts up "--login-server=$Hub" "--authkey=$Token" "--hostname=$Name" '--accept-dns=false' '--unattended'
Start-Sleep -Seconds 4
$meshIp = (& $ts ip -4 | Select-Object -First 1)

# --- engine + metrics as RESILIENT Scheduled Tasks (SYSTEM, at startup) ---
# Plain `schtasks /Create` sets a 72h ExecutionTimeLimit and no restart, so the
# node silently dies after 3 days. Use explicit settings + a watchdog instead.
$dir = Join-Path $env:ProgramData 'caravan'
New-Item -ItemType Directory -Force -Path $dir | Out-Null

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$onstart = New-ScheduledTaskTrigger -AtStartup

function Register-CaravanTask($taskName, $taskCmd) {
    $action = New-ScheduledTaskAction -Execute $taskCmd
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $onstart `
        -Principal $principal -Settings $settings -Force | Out-Null
    Start-ScheduledTask -TaskName $taskName | Out-Null
}

# engine
$cmdPath = Join-Path $dir 'node.cmd'
Set-Content -Path $cmdPath -Encoding ASCII -Value "@echo off`r`n`"$exe`" $exeArgs"
Register-CaravanTask 'CaravanNode' $cmdPath

# metrics agent (bound to the mesh IP)
$mPath = Join-Path $dir 'metrics.ps1'
$srcMetrics = Join-Path $PSScriptRoot 'metrics.ps1'
if (-not (Test-Path $srcMetrics)) {
    Write-Host '[caravan] fetching metrics.ps1'
    $url = 'https://raw.githubusercontent.com/leodev-2022/caravan/main/tools/metrics.ps1'
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $srcMetrics -TimeoutSec 60
}
Copy-Item -Force $srcMetrics $mPath
$mCmd = Join-Path $dir 'metrics.cmd'
Set-Content -Path $mCmd -Encoding ASCII -Value "@echo off`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"$mPath`" -BindHost $meshIp -Port $MetricsPort"
Register-CaravanTask 'CaravanMetrics' $mCmd

# engine + metrics are reached over the mesh; allow them on every firewall
# profile so the node is reachable headless (no interactive logon / NLA settle).
foreach ($p in @($Port, $MetricsPort)) {
    if (-not (Get-NetFirewallRule -DisplayName "Caravan $p" -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName "Caravan $p" -Direction Inbound -Action Allow `
            -Protocol TCP -LocalPort $p -Profile Any -ErrorAction SilentlyContinue | Out-Null
    }
}

# watchdog: every few minutes, restart whichever service is not listening
$wdPath = Join-Path $dir 'watchdog.ps1'
$wd = @'
$ErrorActionPreference = 'SilentlyContinue'
function Ensure($port, $task) {
  if (-not (Get-NetTCPConnection -State Listen -LocalPort $port)) { Start-ScheduledTask -TaskName $task }
}
Ensure __PORT__ 'CaravanNode'
Ensure __METRICS_PORT__ 'CaravanMetrics'
'@
$wd = $wd -replace '__PORT__', $Port -replace '__METRICS_PORT__', $MetricsPort
Set-Content -Path $wdPath -Encoding ASCII -Value $wd
$wdAction = New-ScheduledTaskAction -Execute 'powershell' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$wdPath`""
$wdTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes $WatchdogMinutes)
Register-ScheduledTask -TaskName 'CaravanWatchdog' -Action $wdAction -Trigger $wdTrigger `
    -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName 'CaravanWatchdog' | Out-Null

Write-Host "[caravan] DONE. $Name mesh-ip=$meshIp port=$Port"
Write-Host "[caravan] register on the hub: portal Invite -> Add (name=$Name ip=$meshIp port=$Port)"
Write-Host '[caravan] uninstall: schtasks /Delete /TN CaravanNode /F ; schtasks /Delete /TN CaravanMetrics /F ; schtasks /Delete /TN CaravanWatchdog /F'
