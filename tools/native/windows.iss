#define AppName "LOD pane Word"
#define AppVersion "0.8.0"
#define AppExe "LOD-pane-Word.exe"

[Setup]
AppId={{A39D3C6B-1D67-4C77-B9A1-42E1F51A5001}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\LOD pane Word
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64
OutputDir=..\..\dist
OutputBaseFilename=lod-pane-word-windows-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
Uninstallable=yes
CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\..\dist\LOD-pane-Word\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autoprograms}\{#AppName}\Start companion"; Filename: "{app}\{#AppExe}"; Parameters: "start"
Name: "{autoprograms}\{#AppName}\Stop companion"; Filename: "{app}\{#AppExe}"; Parameters: "stop"
Name: "{autoprograms}\{#AppName}\Status"; Filename: "{app}\{#AppExe}"; Parameters: "status"
Name: "{autoprograms}\{#AppName}\Uninstall"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExe}"; Parameters: "install"; Description: "Set up LOD pane Word"; Flags: postinstall skipifsilent

[Code]
function StopInstalledCompanion(): Boolean;
var
  ResultCode: Integer;
  InstalledExe: String;
begin
  Result := True;
  InstalledExe := ExpandConstant('{localappdata}\Programs\LOD pane Word\{#AppExe}');
  if FileExists(InstalledExe) then begin
    if not Exec(InstalledExe, 'stop --no-dialog', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      ResultCode := -1;
    if ResultCode <> 0 then begin
      MsgBox('LOD pane Word could not stop the installed companion. Close Word or retry Stop from the existing app, then run setup again.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function InitializeSetup(): Boolean;
begin
  Result := StopInstalledCompanion();
end;

function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
  InstalledExe: String;
begin
  Result := True;
  InstalledExe := ExpandConstant('{app}\{#AppExe}');
  if FileExists(InstalledExe) then begin
    if not Exec(InstalledExe, 'uninstall --no-dialog', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      ResultCode := -1;
    if ResultCode <> 0 then begin
      MsgBox('LOD pane Word could not remove its startup and Word registration. The application was kept installed so you can retry cleanup.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;
