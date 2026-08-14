#define MyAppName "translationCore AI Bridge"
#define MyAppVersion "0.7.0"
#define MyAppExeName "translationCore-AI-Bridge-v0.7.0.exe"
#define MyAppPublisher "translationCore AI Bridge"

[Setup]
AppId={{3B359B7A-8386-4B36-904F-4F7F1AF46B60}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion=0.7.0.0
VersionInfoDescription=AI-assisted Bible translation and checking workbench
DefaultDirName={localappdata}\Programs\translationCore AI Bridge
DefaultGroupName=translationCore AI Bridge
DisableProgramGroupPage=yes
OutputDir=..\dist-installer
OutputBaseFilename=translationCore-AI-Bridge-v0.7.0-Setup
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
MinVersion=10.0
CloseApplications=yes
RestartApplications=yes
SetupLogging=yes
UsePreviousAppDir=yes

[Files]
Source: "..\dist\translationCore-AI-Bridge-v0.7.0\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\translationCore AI Bridge"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\User Guide"; Filename: "{app}\_internal\userguide\index.html"; Check: FileExists(ExpandConstant('{app}\_internal\userguide\index.html'))
Name: "{autodesktop}\translationCore AI Bridge"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch translationCore AI Bridge"; Flags: nowait postinstall skipifsilent
Filename: "{app}\_internal\userguide\index.html"; Description: "Open the User Guide"; Flags: shellexec postinstall skipifsilent unchecked; Check: FileExists(ExpandConstant('{app}\_internal\userguide\index.html'))

[Code]
function GitAvailable(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/C where git.exe >NUL 2>NUL', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if not GitAvailable() then
      Log('Git for Windows was not detected. Core application remains fully usable; Git checkpoint/history features will be unavailable until Git is installed.');
  end;
end;
