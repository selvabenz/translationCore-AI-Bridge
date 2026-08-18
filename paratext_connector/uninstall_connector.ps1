[CmdletBinding()]
param([string]$ParatextInstallDir = '', [switch]$Elevated)
$ErrorActionPreference='Stop'

if (Get-Process -Name 'Paratext' -ErrorAction SilentlyContinue) {
    Write-Host 'ERROR: Close Paratext completely before removing the connector.' -ForegroundColor Red
    exit 5
}

function Resolve-ParatextDir {
    param([string]$Explicit)
    $candidates=@()
    if($Explicit){$candidates+=$Explicit}
    if($env:ParatextInstallDir){$candidates+=$env:ParatextInstallDir}
    foreach($regPath in @(
      'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
      'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
      'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*')) {
      try {$candidates += (Get-ItemProperty $regPath -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like 'Paratext 9*' -and $_.InstallLocation } | ForEach-Object {$_.InstallLocation})} catch {}
    }
    if($env:ProgramFiles){$candidates+=(Join-Path $env:ProgramFiles 'Paratext 9')}
    if(${env:ProgramFiles(x86)}){$candidates+=(Join-Path ${env:ProgramFiles(x86)} 'Paratext 9')}
    if($env:LOCALAPPDATA){$candidates+=(Join-Path $env:LOCALAPPDATA 'Programs\Paratext 9')}
    foreach($dir in ($candidates | Select-Object -Unique)){
      if($dir -and (Test-Path (Join-Path $dir 'Paratext.exe'))){return (Resolve-Path $dir).Path}
    }
    throw 'Could not locate Paratext 9. Pass -ParatextInstallDir explicitly.'
}

$dir=Resolve-ParatextDir $ParatextInstallDir
$target=Join-Path $dir 'plugins\translationCoreAIBridge'
try { if(Test-Path $target){Remove-Item $target -Recurse -Force} }
catch [System.UnauthorizedAccessException] {
  if($Elevated){throw}
  $args=@('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$MyInvocation.MyCommand.Path+'"'),'-Elevated','-ParatextInstallDir',('"'+$dir+'"'))
  $p=Start-Process powershell.exe -ArgumentList ($args -join ' ') -Verb RunAs -Wait -PassThru
  exit $p.ExitCode
}
Write-Host 'Paratext AI Bridge Connector removed.' -ForegroundColor Green
