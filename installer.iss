; Inno Setup script - builds iOSPair-Setup.exe
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6C0E8B1E-6F2B-4E7A-9D7C-2A1F4B8E3C51}
AppName=iOSPair
AppVersion={#AppVersion}
AppPublisher=iOSPair
DefaultDirName={autopf}\iOSPair
DefaultGroupName=iOSPair
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=iOSPair-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\iOSPair.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0

[Languages]
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\iOSPair.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\iOSPair"; Filename: "{app}\iOSPair.exe"
Name: "{autodesktop}\iOSPair"; Filename: "{app}\iOSPair.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\iOSPair.exe"; Description: "{cm:LaunchProgram,iOSPair}"; Flags: nowait postinstall skipifsilent
