; Inno Setup script for OneAudio. Build with build.ps1 (it runs PyInstaller first).
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E0A3C1D-8F2B-4C7E-9A51-0B7D2E4F6A13}
AppName=OneAudio
AppVersion={#AppVersion}
AppPublisher=Escillex
AppPublisherURL=https://github.com/Escillex/OneAudio
DefaultDirName={autopf}\OneAudio
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ChangesEnvironment=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=OneAudio-Setup-{#AppVersion}
UninstallDisplayIcon={app}\oneaudio-receive.exe
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
VersionInfoVersion={#AppVersion}
; Same AppId = upgrades in place (keeps install dir and task choices).
; Close running oneaudio-send/receive/tray so their files can be replaced.
CloseApplications=force
RestartApplications=no

[Tasks]
Name: addtopath; Description: "Add OneAudio to PATH (use oneaudio-send / oneaudio-receive from any terminal)"
Name: firewall; Description: "Allow the receiver through Windows Firewall (Private networks)"
Name: startmenu; Description: "Start menu shortcuts (OneAudio Sender / Receiver, run in the tray)"
Name: desktopicon; Description: "Desktop shortcuts"; Flags: unchecked

[Files]
Source: "..\dist\oneaudio-send.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\oneaudio-receive.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\oneaudio-tray.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; oneaudio-tray.exe is the windowed build, so no console flashes up.
Name: "{autoprograms}\OneAudio Sender"; Filename: "{app}\oneaudio-tray.exe"; Parameters: "send"; Tasks: startmenu
Name: "{autoprograms}\OneAudio Receiver"; Filename: "{app}\oneaudio-tray.exe"; Parameters: "receive"; Tasks: startmenu
Name: "{autodesktop}\OneAudio Sender"; Filename: "{app}\oneaudio-tray.exe"; Parameters: "send"; Tasks: desktopicon
Name: "{autodesktop}\OneAudio Receiver"; Filename: "{app}\oneaudio-tray.exe"; Parameters: "receive"; Tasks: desktopicon

[Registry]
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
  ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; \
  Check: NeedsAddPath(ExpandConstant('{app}')); Tasks: addtopath

[Run]
; Delete first so reinstalling doesn't stack duplicate rules.
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""OneAudio Receiver"""; \
  Flags: runhidden; Tasks: firewall
Filename: "{sys}\netsh.exe"; \
  Parameters: "advfirewall firewall add rule name=""OneAudio Receiver"" dir=in action=allow program=""{app}\oneaudio-receive.exe"" protocol=UDP profile=private enable=yes"; \
  Flags: runhidden; Tasks: firewall
Filename: "{sys}\netsh.exe"; \
  Parameters: "advfirewall firewall add rule name=""OneAudio Receiver"" dir=in action=allow program=""{app}\oneaudio-tray.exe"" protocol=UDP profile=private enable=yes"; \
  Flags: runhidden; Tasks: firewall
; "Install update" from the tray passes /RELAUNCH=send|receive to reopen it afterwards.
Filename: "{app}\oneaudio-tray.exe"; Parameters: "send"; Flags: nowait runasoriginaluser; Check: Relaunch('send')
Filename: "{app}\oneaudio-tray.exe"; Parameters: "receive"; Flags: nowait runasoriginaluser; Check: Relaunch('receive')

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""OneAudio Receiver"""; \
  Flags: runhidden; RunOnceId: "DelFirewallRule"

[Code]
const
  EnvKey = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';

function NeedsAddPath(Dir: string): Boolean;
var
  Path: string;
begin
  if not RegQueryStringValue(HKLM, EnvKey, 'Path', Path) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Path) + ';') = 0;
end;

function Relaunch(Role: string): Boolean;
begin
  Result := CompareText(ExpandConstant('{param:RELAUNCH|}'), Role) = 0;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Path, Dir: string;
  P: Integer;
begin
  if CurUninstallStep <> usPostUninstall then
    exit;
  if not RegQueryStringValue(HKLM, EnvKey, 'Path', Path) then
    exit;
  Dir := ExpandConstant('{app}');
  P := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Path) + ';');
  if P = 0 then
    exit;
  // P indexes into ';' + Path + ';', so it lands on the separator before Dir in Path.
  if P = 1 then
    Delete(Path, 1, Length(Dir) + 1)
  else
    Delete(Path, P - 1, Length(Dir) + 1);
  RegWriteExpandStringValue(HKLM, EnvKey, 'Path', Path);
end;
