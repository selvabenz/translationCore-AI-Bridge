[CmdletBinding()]
param([string]$ParatextInstallDir = '')

$ErrorActionPreference = 'Stop'

function Resolve-ParatextDir {
    param([string]$Explicit)
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($Explicit) { $candidates.Add($Explicit) }
    if ($env:ParatextInstallDir) { $candidates.Add($env:ParatextInstallDir) }
    foreach ($regPath in @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*')) {
        try {
            Get-ItemProperty $regPath -ErrorAction SilentlyContinue |
                Where-Object { $_.DisplayName -like 'Paratext 9*' -and $_.InstallLocation } |
                ForEach-Object { $candidates.Add([string]$_.InstallLocation) }
        } catch { }
    }
    if ($env:ProgramFiles) { $candidates.Add((Join-Path $env:ProgramFiles 'Paratext 9')) }
    if (${env:ProgramFiles(x86)}) { $candidates.Add((Join-Path ${env:ProgramFiles(x86)} 'Paratext 9')) }
    if ($env:LOCALAPPDATA) { $candidates.Add((Join-Path $env:LOCALAPPDATA 'Programs\Paratext 9')) }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not $candidate) { continue }
        $expanded = [Environment]::ExpandEnvironmentVariables($candidate.Trim('"'))
        if (Test-Path (Join-Path $expanded 'Paratext.exe')) { return (Resolve-Path $expanded).Path }
    }
    return ''
}

function Get-AssemblyIdentity {
    param([System.IO.FileInfo]$File)
    try {
        $name = [Reflection.AssemblyName]::GetAssemblyName($File.FullName)
        return ($name.Name + ', Version=' + $name.Version.ToString())
    } catch {
        return $File.Name
    }
}

Write-Host ''
Write-Host 'translationCore AI Bridge v0.7.4 - Paratext Connector Diagnostics' -ForegroundColor Cyan
Write-Host 'Targeted field-test version: Paratext 9.5.110.1'
Write-Host ''

$pt = Resolve-ParatextDir $ParatextInstallDir
if (-not $pt) {
    Write-Host 'Paratext installation: NOT FOUND' -ForegroundColor Red
    Write-Host 'Re-run with the installation folder, for example:'
    Write-Host '  diagnose_paratext_connector.bat "C:\Program Files\Paratext 9"'
    exit 2
}
Write-Host "Paratext installation: $pt" -ForegroundColor Green
$exe = Join-Path $pt 'Paratext.exe'
try { Write-Host ('Paratext file version: ' + (Get-Item $exe).VersionInfo.FileVersion) } catch { }

$interfaces = @(Get-ChildItem -Path $pt -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -eq 'PluginInterfaces.dll' -or
        $_.Name -eq 'CorePluginInterfaces.dll' -or
        $_.Name -eq 'ParatextCorePluginInterfaces.dll' -or
        $_.Name -match 'PluginInterfaces.*\.dll$'
    } |
    Sort-Object FullName -Unique)
if ($interfaces.Count -eq 0) {
    Write-Host 'Paratext interface assemblies: NOT FOUND' -ForegroundColor Red
} else {
    Write-Host "Paratext interface assemblies: $($interfaces.Count) found" -ForegroundColor Green
    $interfaces | ForEach-Object { Write-Host ('  ' + $_.FullName + '  [' + (Get-AssemblyIdentity $_) + ']') }
}

$pluginInterface = @($interfaces | Where-Object { $_.Name -eq 'PluginInterfaces.dll' } | Select-Object -First 1)
$coreRequired = $false
if ($pluginInterface.Count -gt 0) {
    try {
        $metadata = [Reflection.Assembly]::ReflectionOnlyLoadFrom($pluginInterface[0].FullName)
        $coreRequired = @($metadata.GetReferencedAssemblies() | Where-Object { $_.Name -eq 'CorePluginInterfaces' -or $_.Name -eq 'ParatextCorePluginInterfaces' }).Count -gt 0
    } catch {
        Write-Host ('PluginInterfaces dependency inspection: unavailable (' + $_.Exception.Message + ')') -ForegroundColor Yellow
    }
}
$coreFound = @($interfaces | Where-Object {
    try { $n = [Reflection.AssemblyName]::GetAssemblyName($_.FullName).Name; $n -eq 'CorePluginInterfaces' -or $n -eq 'ParatextCorePluginInterfaces' }
    catch { $_.Name -eq 'CorePluginInterfaces.dll' -or $_.Name -eq 'ParatextCorePluginInterfaces.dll' }
}).Count -gt 0
if ($coreRequired) {
    if ($coreFound) {
        Write-Host 'CorePluginInterfaces dependency: required and FOUND' -ForegroundColor Green
    } else {
        Write-Host 'CorePluginInterfaces dependency: required but NOT FOUND' -ForegroundColor Red
    }
} else {
    Write-Host 'CorePluginInterfaces dependency: not detected (older interface versions may not require it)'
}

$cscs = @(
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')) | Where-Object { Test-Path $_ }
if ($cscs.Count -eq 0) {
    Write-Host '.NET Framework C# compiler: NOT FOUND' -ForegroundColor Red
} else {
    Write-Host ('.NET Framework C# compiler: ' + $cscs[0]) -ForegroundColor Green
    try { Write-Host ('C# compiler file version: ' + (Get-Item $cscs[0]).VersionInfo.FileVersion) } catch { }
}

$facades = New-Object System.Collections.Generic.List[string]
foreach ($programFilesRoot in @(${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
    if (-not $programFilesRoot) { continue }
    $refRoot = Join-Path $programFilesRoot 'Reference Assemblies\Microsoft\Framework\.NETFramework'
    if (Test-Path $refRoot) {
        Get-ChildItem -Path $refRoot -Recurse -Filter 'netstandard.dll' -File -ErrorAction SilentlyContinue |
            Where-Object { $_.DirectoryName -like '*\Facades' } |
            Sort-Object FullName -Descending |
            ForEach-Object { if (-not $facades.Contains($_.FullName)) { $facades.Add($_.FullName) } }
    }
}
if ($cscs.Count -gt 0) {
    foreach ($frameworkRoot in @(
        (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\Facades'),
        (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\Facades')
    )) {
        $runtimeFacade = Join-Path $frameworkRoot 'netstandard.dll'
        if ((Test-Path $runtimeFacade) -and -not $facades.Contains($runtimeFacade)) { $facades.Add($runtimeFacade) }
    }
}
$gacNetstandard = Join-Path $env:WINDIR 'Microsoft.NET\assembly\GAC_MSIL\netstandard'
if (Test-Path $gacNetstandard) {
    Get-ChildItem -Path $gacNetstandard -Recurse -Filter 'netstandard.dll' -File -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        ForEach-Object { if (-not $facades.Contains($_.FullName)) { $facades.Add($_.FullName) } }
}
Get-ChildItem -Path $pt -Recurse -Filter 'netstandard.dll' -File -ErrorAction SilentlyContinue |
    Sort-Object FullName |
    ForEach-Object { if (-not $facades.Contains($_.FullName)) { $facades.Add($_.FullName) } }
if ($facades.Count -gt 0) {
    Write-Host ('netstandard facade: ' + $facades[0]) -ForegroundColor Green
} else {
    Write-Host 'netstandard facade: NOT FOUND' -ForegroundColor Yellow
}

$plugin = Join-Path $pt 'plugins\translationCoreAIBridge\translationCoreAIBridge.ptxplg'
if (Test-Path $plugin) {
    Write-Host "Installed connector: $plugin" -ForegroundColor Green
} else {
    Write-Host 'Installed connector: not installed yet' -ForegroundColor Yellow
}

$running = Get-Process -Name 'Paratext' -ErrorAction SilentlyContinue
Write-Host ('Paratext process: ' + $(if ($running) { 'RUNNING' } else { 'not running' }))

Write-Host ''
$pluginFound = $pluginInterface.Count -gt 0
if ($pluginFound -and $cscs.Count -gt 0 -and (-not $coreRequired -or $coreFound)) {
    Write-Host 'DIAGNOSTIC RESULT: READY TO ATTEMPT CONNECTOR BUILD' -ForegroundColor Green
    Write-Host 'The build step is still the final compatibility test and will now print complete CSxxxx diagnostics.'
    exit 0
}
Write-Host 'DIAGNOSTIC RESULT: REQUIREMENTS MISSING - copy this console output when reporting the problem.' -ForegroundColor Red
exit 3
