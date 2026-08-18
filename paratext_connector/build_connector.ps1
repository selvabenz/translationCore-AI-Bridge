[CmdletBinding()]
param(
    [string]$ParatextInstallDir = ''
)

$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$TargetVersion = '0.7.4'

function Find-ParatextInstall {
    param([string]$Explicit)
    $candidates = New-Object System.Collections.Generic.List[string]
    if ($Explicit) { $candidates.Add($Explicit) }
    if ($env:ParatextInstallDir) { $candidates.Add($env:ParatextInstallDir) }

    $regPaths = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    foreach ($regPath in $regPaths) {
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
        $resolved = [Environment]::ExpandEnvironmentVariables($candidate.Trim('"'))
        if (Test-Path (Join-Path $resolved 'Paratext.exe')) { return (Resolve-Path $resolved).Path }
    }
    throw "Could not locate Paratext 9. Re-run with -ParatextInstallDir 'C:\path\to\Paratext 9'."
}

function Find-CSharpCompiler {
    $paths = @(
        (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
        (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
    )
    foreach ($p in $paths) { if (Test-Path $p) { return $p } }
    throw 'Windows .NET Framework C# compiler (csc.exe) was not found. Enable/install .NET Framework 4.8 and retry.'
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

function Add-CandidateFile {
    param(
        [System.Collections.Generic.List[System.IO.FileInfo]]$List,
        [string]$Path
    )
    if ($Path -and (Test-Path $Path)) {
        $List.Add((Get-Item $Path))
    }
}

$ParatextDir = Find-ParatextInstall $ParatextInstallDir
$Csc = Find-CSharpCompiler
$FrameworkDir = Split-Path -Parent $Csc
$WebExtensions = Join-Path $FrameworkDir 'System.Web.Extensions.dll'
if (-not (Test-Path $WebExtensions)) { throw 'Missing System.Web.Extensions.dll beside the Windows .NET Framework compiler.' }

# Prefer assemblies in the Paratext application root, then fall back to recursive discovery.
# ParatextPluginInterfaces 2.0.100 forwards many contracts into a separate core assembly.
# The NuGet package is named ParatextCorePluginInterfaces, while the installed DLL/assembly
# identity used by Paratext 9.5.110.1 is CorePluginInterfaces. Search both names and then
# resolve the dependency by assembly identity rather than trusting a package/file name.
$interfaceCandidates = New-Object 'System.Collections.Generic.List[System.IO.FileInfo]'
foreach ($name in @('PluginInterfaces.dll', 'CorePluginInterfaces.dll', 'ParatextCorePluginInterfaces.dll')) {
    Add-CandidateFile $interfaceCandidates (Join-Path $ParatextDir $name)
}
Get-ChildItem -Path $ParatextDir -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -eq 'PluginInterfaces.dll' -or
        $_.Name -eq 'CorePluginInterfaces.dll' -or
        $_.Name -eq 'ParatextCorePluginInterfaces.dll' -or
        $_.Name -match 'PluginInterfaces.*\.dll$'
    } |
    Sort-Object FullName |
    ForEach-Object { $interfaceCandidates.Add($_) }

$interfaceDlls = @()
$seenAssemblies = @{}
foreach ($dll in $interfaceCandidates) {
    try { $simple = [Reflection.AssemblyName]::GetAssemblyName($dll.FullName).Name } catch { $simple = $dll.Name }
    if (-not $seenAssemblies.ContainsKey($simple)) {
        $seenAssemblies[$simple] = $true
        $interfaceDlls += $dll
    }
}

$pluginInterfaces = @($interfaceDlls | Where-Object {
    try { [Reflection.AssemblyName]::GetAssemblyName($_.FullName).Name -eq 'PluginInterfaces' } catch { $_.Name -eq 'PluginInterfaces.dll' }
})
if ($pluginInterfaces.Count -eq 0) {
    throw "No Paratext PluginInterfaces.dll assembly was found under $ParatextDir. Run diagnose_paratext_connector.bat and send its output."
}

# Inspect the installed PluginInterfaces metadata to detect the modern core dependency. This is
# advisory if reflection-only metadata inspection is unavailable, but a missing known dependency
# becomes a clear pre-build error instead of an opaque CS0012 later.
$coreDependencyRequired = $false
$coreDependencyName = ''
$coreDependencyNames = @('CorePluginInterfaces', 'ParatextCorePluginInterfaces')
try {
    $metadataAssembly = [Reflection.Assembly]::ReflectionOnlyLoadFrom($pluginInterfaces[0].FullName)
    $coreReference = @($metadataAssembly.GetReferencedAssemblies() | Where-Object { $coreDependencyNames -contains $_.Name } | Select-Object -First 1)
    if ($coreReference.Count -gt 0) {
        $coreDependencyRequired = $true
        $coreDependencyName = [string]$coreReference[0].Name
    }
} catch {
    # csc.exe remains the source of truth; do not reject a valid older Paratext assembly merely
    # because reflection-only inspection was unavailable on this computer.
}
$coreInterfaces = @($interfaceDlls | Where-Object {
    try { $coreDependencyNames -contains [Reflection.AssemblyName]::GetAssemblyName($_.FullName).Name } catch {
        $_.Name -eq 'CorePluginInterfaces.dll' -or $_.Name -eq 'ParatextCorePluginInterfaces.dll'
    }
})
if ($coreDependencyRequired -and $coreInterfaces.Count -eq 0) {
    throw "The installed PluginInterfaces.dll depends on $coreDependencyName, but no matching core PluginInterfaces assembly was found under $ParatextDir. Expected a DLL such as CorePluginInterfaces.dll. Run diagnose_paratext_connector.bat and send its output."
}

# Locate the .NET Standard 2.0 facade used by current Paratext PluginInterfaces. Prefer .NET
# Framework reference assemblies, then framework/GAC facades, then a copy shipped with Paratext.
$netstandardCandidates = New-Object System.Collections.Generic.List[string]
foreach ($programFilesRoot in @(${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
    if (-not $programFilesRoot) { continue }
    $refRoot = Join-Path $programFilesRoot 'Reference Assemblies\Microsoft\Framework\.NETFramework'
    if (Test-Path $refRoot) {
        Get-ChildItem -Path $refRoot -Recurse -Filter 'netstandard.dll' -File -ErrorAction SilentlyContinue |
            Where-Object { $_.DirectoryName -like '*\Facades' } |
            Sort-Object FullName -Descending |
            ForEach-Object { if (-not $netstandardCandidates.Contains($_.FullName)) { $netstandardCandidates.Add($_.FullName) } }
    }
}
foreach ($frameworkRoot in @(
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\Facades'),
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\Facades')
)) {
    if (-not $frameworkRoot) { continue }
    $candidate = Join-Path $frameworkRoot 'netstandard.dll'
    if ((Test-Path $candidate) -and -not $netstandardCandidates.Contains($candidate)) { $netstandardCandidates.Add($candidate) }
}
$gacNetstandard = Join-Path $env:WINDIR 'Microsoft.NET\assembly\GAC_MSIL\netstandard'
if (Test-Path $gacNetstandard) {
    Get-ChildItem -Path $gacNetstandard -Recurse -Filter 'netstandard.dll' -File -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        ForEach-Object { if (-not $netstandardCandidates.Contains($_.FullName)) { $netstandardCandidates.Add($_.FullName) } }
}
Get-ChildItem -Path $ParatextDir -Recurse -Filter 'netstandard.dll' -File -ErrorAction SilentlyContinue |
    Sort-Object FullName |
    ForEach-Object { if (-not $netstandardCandidates.Contains($_.FullName)) { $netstandardCandidates.Add($_.FullName) } }

$OutDir = Join-Path $Here 'dist'
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$DllOut = Join-Path $OutDir 'translationCoreAIBridge.dll'
$PluginOut = Join-Path $OutDir 'translationCoreAIBridge.ptxplg'
Remove-Item $DllOut,$PluginOut -Force -ErrorAction SilentlyContinue

$sources = @(
    (Join-Path $Here 'BridgeProtocol.cs'),
    (Join-Path $Here 'NamedPipeBridgeServer.cs'),
    (Join-Path $Here 'AiBridgeConnectorPlugin.cs')
)
foreach ($source in $sources) { if (-not (Test-Path $source)) { throw "Missing connector source: $source" } }

$compileArgs = New-Object System.Collections.Generic.List[string]
$compileArgs.Add('/nologo')
$compileArgs.Add('/target:library')
$compileArgs.Add('/optimize+')
$compileArgs.Add('/platform:anycpu')
$compileArgs.Add('/utf8output')
$compileArgs.Add('/warn:4')
$compileArgs.Add('/out:' + $DllOut)
$compileArgs.Add('/reference:' + $WebExtensions)
if ($netstandardCandidates.Count -gt 0) { $compileArgs.Add('/reference:' + $netstandardCandidates[0]) }
foreach ($dll in $interfaceDlls) { $compileArgs.Add('/reference:' + $dll.FullName) }
foreach ($source in $sources) { $compileArgs.Add($source) }

Write-Host ''
Write-Host 'translationCore AI Bridge v0.7.4 - Paratext Live Connector builder' -ForegroundColor Cyan
Write-Host "Paratext installation : $ParatextDir"
try {
    $pv = (Get-Item (Join-Path $ParatextDir 'Paratext.exe')).VersionInfo.FileVersion
    Write-Host "Paratext file version : $pv"
    if ($pv -and -not $pv.StartsWith('9.5.110.1')) {
        Write-Host 'NOTE: v0.7.4 field certification targets Paratext 9.5.110.1. This build will still use the interfaces from the installed version, but should be re-certified.' -ForegroundColor Yellow
    }
} catch { }
Write-Host "C# compiler           : $Csc"
try { Write-Host ('C# compiler version   : ' + (Get-Item $Csc).VersionInfo.FileVersion) } catch { }
Write-Host 'Paratext interface references:'
$interfaceDlls | ForEach-Object { Write-Host ('  ' + $_.FullName + '  [' + (Get-AssemblyIdentity $_) + ']') }
if ($netstandardCandidates.Count -gt 0) {
    Write-Host ('netstandard facade    : ' + $netstandardCandidates[0])
} else {
    Write-Host 'netstandard facade    : NOT FOUND (csc will report whether the installed interfaces require it)' -ForegroundColor Yellow
}
Write-Host ''
Write-Host 'C# compiler diagnostics:' -ForegroundColor Cyan

# Capture both stdout and stderr, then always print them before evaluating the exit code. This
# prevents the installer wrapper from hiding the actual CSxxxx diagnostic that caused a failure.
$compilerOutput = @(& $Csc @compileArgs 2>&1)
$compilerExitCode = $LASTEXITCODE
if ($compilerOutput.Count -eq 0) {
    Write-Host '  (compiler produced no console text)'
} else {
    $compilerOutput | ForEach-Object { Write-Host ([string]$_) }
}

if ($compilerExitCode -ne 0 -or -not (Test-Path $DllOut)) {
    throw "Connector compilation failed (csc exit code $compilerExitCode). The complete compiler diagnostics are printed immediately above this line."
}
Copy-Item $DllOut $PluginOut -Force
Remove-Item $DllOut -Force -ErrorAction SilentlyContinue

Write-Host ''
Write-Host 'CONNECTOR BUILD PASSED' -ForegroundColor Green
Write-Host "Built: $PluginOut"
Write-Host 'This plugin was compiled against the PluginInterfaces assemblies in your installed Paratext.'
Write-Output $PluginOut
