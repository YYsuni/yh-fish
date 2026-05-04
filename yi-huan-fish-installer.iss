; Inno Setup 6 — 由 scripts/build-release.ps1 调用 ISCC 并传入 /D 宏（避免 include 文件编码问题）
; 手动编译示例: ISCC /DMyAppVersion=1.0.0 /DMyAppName=异环钓鱼工具 /DMyAppBuildDir=release/app/异环钓鱼工具 yi-huan-fish-installer.iss

#ifndef MyAppVersion
#define MyAppVersion "0.0.0"
#endif
#ifndef MyAppName
#define MyAppName "异环钓鱼工具"
#endif
#ifndef MyAppBuildDir
#define MyAppBuildDir "release/app/异环钓鱼工具"
#endif

#define MyAppExeName MyAppName + ".exe"

[Setup]
AppId={{C4F2A91E-8B3D-4E6F-9A12-5BC8D7E6F102}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=yh-fish
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=release
OutputBaseFilename={#MyAppName}-{#MyAppVersion}-setup
SetupIconFile=release/app-icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
DisableProgramGroupPage=no
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#MyAppBuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
