[CmdletBinding()]
param(
    [string]$ParatextInstallDir = '',
    [string]$BuiltPlugin = '',
    [switch]$SkipBuild,
    [switch]$Elevated
)

$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

# Do not try to replace a plugin while Paratext has loaded it.
if (Get-Process -Name 'Paratext' -ErrorAction SilentlyContinue) {
    Write-Host 'ERROR: Paratext is running.' -ForegroundColor Red
    Write-Host 'Close Paratext completely, then run this installer again.'
    exit 5
}

if (-not $SkipBuild) {
    # Do not capture build_connector.ps1 output into a variable. Native csc.exe writes its useful
    # CSxxxx diagnostics to the success/output stream; capturing this pipeline hid those diagnostics
    # when the build subsequently threw. The output path is deterministic, so no parsing is needed.
    & (Join-Path $Here 'build_connector.ps1') -ParatextInstallDir $ParatextInstallDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $BuiltPlugin = Join-Path $Here 'dist\translationCoreAIBridge.ptxplg'
}
if (-not (Test-Path $BuiltPlugin)) { throw "Built connector was not found: $BuiltPlugin" }

# Re-use the same deterministic Paratext discovery as the builder without compiling twice.
function Resolve-ParatextDir {
    param([string]$Explicit)
    $candidates = @()
    if ($Explicit) { $candidates += $Explicit }
    if ($env:ParatextInstallDir) { $candidates += $env:ParatextInstallDir }
    foreach ($regPath in @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*','HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*')) {
        try { $candidates += (Get-ItemProperty $regPath -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like 'Paratext 9*' -and $_.InstallLocation } | ForEach-Object { $_.InstallLocation }) } catch { }
    }
    if ($env:ProgramFiles) { $candidates += (Join-Path $env:ProgramFiles 'Paratext 9') }
    if (${env:ProgramFiles(x86)}) { $candidates += (Join-Path ${env:ProgramFiles(x86)} 'Paratext 9') }
    if ($env:LOCALAPPDATA) { $candidates += (Join-Path $env:LOCALAPPDATA 'Programs\Paratext 9') }
    foreach ($c in ($candidates | Select-Object -Unique)) {
        if ($c -and (Test-Path (Join-Path $c 'Paratext.exe'))) { return (Resolve-Path $c).Path }
    }
    throw "Could not locate Paratext 9. Re-run with -ParatextInstallDir 'C:\path\to\Paratext 9'."
}

$ParatextDir = Resolve-ParatextDir $ParatextInstallDir
$TargetDir = Join-Path $ParatextDir 'plugins\translationCoreAIBridge'
$Target = Join-Path $TargetDir 'translationCoreAIBridge.ptxplg'

try {
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
    Copy-Item $BuiltPlugin $Target -Force
} catch [System.UnauthorizedAccessException] {
    if ($Elevated) { throw }
    Write-Host 'Administrator permission is required to install into the Paratext program folder.' -ForegroundColor Yellow
    $argList = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $MyInvocation.MyCommand.Path + '"'),'-SkipBuild','-Elevated','-ParatextInstallDir',('"' + $ParatextDir + '"'),'-BuiltPlugin',('"' + $BuiltPlugin + '"'))
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ($argList -join ' ') -Verb RunAs -Wait -PassThru
    exit $p.ExitCode
}

if (-not (Test-Path $Target)) { throw 'Connector copy did not complete.' }
Write-Host ''
Write-Host 'PARATEXT CONNECTOR INSTALLED' -ForegroundColor Green
Write-Host "Installed: $Target"
Write-Host ''
Write-Host 'Next:'
Write-Host '  1. Start Paratext 9.5 and open your Scripture project.'
Write-Host '  2. Put the active Paratext window in scroll/sync group A-E.'
Write-Host '  3. Start translationCore AI Bridge v0.7.5.'
Write-Host '  4. Production > Paratext Live Connector > Connect / Refresh.'
Write-Host '  5. Enable Sync verse navigation when the connection is green.'
exit 0
