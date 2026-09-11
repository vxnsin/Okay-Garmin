; Inno Setup script for Okay-Garmin.
;
; Per-user install: no administrator rights, which matches the HKCU autostart
; entry the application writes. Compiled by .github/workflows/release.yml, or
; locally by build.ps1 when Inno Setup 6 is installed.
;
;   ISCC.exe /DAppVersion=2.0.0 installer\okay-garmin.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "Okay-Garmin"
#define AppPublisher "Vensin"
#define AppURL "https://github.com/vxnsin/Okay-Garmin"
#define AppExe "Okay-Garmin.exe"

[Setup]
AppId={{8E4C1F62-6D3A-4F58-9B2E-7A15C0D9E413}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases

; Per-user: installs under %LOCALAPPDATA%\Programs and never prompts for admin.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto

OutputDir=..\dist\installer
OutputBaseFilename=Okay-Garmin-Setup-{#AppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; The updater downloads and runs this silently.
CloseApplications=force
RestartApplications=no

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
de.AutostartTask=Mit Windows starten
de.DesktopTask=Verknüpfung auf dem Desktop anlegen
de.LaunchApp={#AppName} jetzt starten
de.ModelNote=Beim ersten Start lädt {#AppName} einmalig rund 190 MB Sprachmodelle herunter. Danach arbeitet die Erkennung vollständig offline.
en.AutostartTask=Start with Windows
en.DesktopTask=Create a desktop shortcut
en.LaunchApp=Launch {#AppName} now
en.ModelNote=On first start {#AppName} downloads about 190 MB of speech models, once. After that recognition runs entirely offline.

[Tasks]
Name: "autostart"; Description: "{cm:AutostartTask}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "desktopicon"; Description: "{cm:DesktopTask}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\update.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\sounds\*"; DestDir: "{app}\sounds"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Quoted on purpose: an unquoted path breaks as soon as a directory contains a
; space. The application reads and repairs this same value.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"""; \
    Flags: uninsdeletevalue; Tasks: autostart
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: none; ValueName: "{#AppName}"; \
    Flags: deletevalue uninsdeletevalue; Tasks: not autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; \
    Flags: nowait postinstall skipifsilent
; After a silent update the app has to come back on its own.
Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: WasSilent

[UninstallDelete]
; Leave %APPDATA%\Okay-Garmin alone -- config, logs and the downloaded models
; live there, and the user is asked separately whether to remove them.
Type: filesandordirs; Name: "{app}"

[Code]
function WasSilent: Boolean;
begin
  Result := WizardSilent;
end;

procedure InitializeWizard;
begin
  CreateOutputMsgPage(
    wpSelectTasks,
    SetupMessage(msgWizardInfoBefore),
    '',
    ExpandConstant('{cm:ModelNote}'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\{#AppName}');
    if DirExists(DataDir) then
    begin
      if SuppressibleMsgBox(
           'Remove settings, logs and the downloaded speech models too?' + #13#10 + DataDir,
           mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;

// The language chosen here becomes the application's initial UI language.
procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigDir, ConfigFile, Language: String;
begin
  if CurStep = ssPostInstall then
  begin
    ConfigDir := ExpandConstant('{userappdata}\{#AppName}');
    ConfigFile := ConfigDir + '\config.json';

    // Only seed a fresh install; never overwrite an existing configuration.
    if not FileExists(ConfigFile) then
    begin
      if ActiveLanguage = 'de' then
        Language := 'de'
      else
        Language := 'en';

      ForceDirectories(ConfigDir);
      SaveStringToFile(
        ConfigFile,
        '{' + #13#10 +
        '    "schema_version": 3,' + #13#10 +
        '    "ui_language": "' + Language + '"' + #13#10 +
        '}' + #13#10,
        False);
    end;
  end;
end;
