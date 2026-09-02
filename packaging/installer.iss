#ifndef AppVersion
  #define AppVersion "0.5.0"
#endif

[Setup]
AppId={{5EF4D2CB-4F7E-4E46-9A4C-61EA424CC4BE}
AppName=VibeGap
AppVersion={#AppVersion}
AppPublisher=Ktao
AppPublisherURL=https://github.com/ktao732084-arch/vibegap
AppSupportURL=https://github.com/ktao732084-arch/vibegap/issues
AppUpdatesURL=https://github.com/ktao732084-arch/vibegap/releases
DefaultDirName={localappdata}\Programs\VibeGap
DefaultGroupName=VibeGap
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist\installer
OutputBaseFilename=VibeGap-{#AppVersion}-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
LicenseFile=..\LICENSE
UninstallDisplayIcon={app}\VibeGap.exe
VersionInfoVersion={#AppVersion}.0

[Tasks]
Name: "claude"; Description: "Connect Claude Code hooks"; GroupDescription: "Agent integrations:"; Flags: checkedonce
Name: "codex"; Description: "Connect Codex hooks"; GroupDescription: "Agent integrations:"; Flags: checkedonce
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start VibeGap when I sign in (normally unnecessary)"; GroupDescription: "Optional background behavior:"; Flags: unchecked

[Files]
Source: "..\dist\VibeGap\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\VibeGap"; Filename: "{app}\VibeGap.exe"; Parameters: "--ensure --toggle"; WorkingDir: "{app}"
Name: "{autodesktop}\VibeGap"; Filename: "{app}\VibeGap.exe"; Parameters: "--ensure --toggle"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\VibeGap"; Filename: "{app}\VibeGap.exe"; Parameters: "--daemon"; WorkingDir: "{app}"; Tasks: startup

[Run]
Filename: "{app}\VibeGap.exe"; Parameters: "--install-agent claude-code --receipt ""{app}\.installer\claude-code.json"""; Flags: runhidden; Tasks: claude
Filename: "{app}\VibeGap.exe"; Parameters: "--install-agent codex --receipt ""{app}\.installer\codex.json"""; Flags: runhidden; Tasks: codex
Filename: "{app}\VibeGap.exe"; Parameters: "--ensure --toggle"; Description: "Launch VibeGap"; Flags: postinstall nowait skipifsilent runhidden

[UninstallRun]
Filename: "{app}\VibeGap.exe"; Parameters: "--uninstall-agent claude-code --receipt ""{app}\.installer\claude-code.json"""; Flags: runhidden skipifdoesntexist; RunOnceId: "RemoveClaudeHooks"
Filename: "{app}\VibeGap.exe"; Parameters: "--uninstall-agent codex --receipt ""{app}\.installer\codex.json"""; Flags: runhidden skipifdoesntexist; RunOnceId: "RemoveCodexHooks"
Filename: "{app}\VibeGap.exe"; Parameters: "--uninstall-agent workbuddy --receipt ""{app}\.installer\workbuddy.json"""; Flags: runhidden skipifdoesntexist; RunOnceId: "RemoveWorkBuddyHooks"
