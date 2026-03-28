#ifndef MyAppName
  #define MyAppName "YOURSHIGUAN Register"
#endif
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#ifndef MyAppPublisher
  #define MyAppPublisher "pengjianzhong"
#endif
#ifndef MyAppPublisherURL
  #define MyAppPublisherURL "https://example.invalid/yourshiguan-register"
#endif
#ifndef MyAppSupportURL
  #define MyAppSupportURL "mailto:pengjianzhong@users.noreply.github.com"
#endif
#ifndef MyAppExeName
  #define MyAppExeName "YOURSHIGUAN_Register.exe"
#endif
#ifndef MySourceExePath
  #define MySourceExePath "YOURSHIGUAN_Register.exe"
#endif
#ifndef MyOutputDir
  #define MyOutputDir "."
#endif
#ifndef MyOutputBaseFilename
  #define MyOutputBaseFilename "YOURSHIGUAN_Register_Setup"
#endif

[Setup]
AppId={{2CBAE3BE-F4E1-4CD6-9D82-387B373A3391}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppPublisherURL}
AppSupportURL={#MyAppSupportURL}
DefaultDirName={localappdata}\YOURSHIGUAN Register
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#MyOutputDir}
OutputBaseFilename={#MyOutputBaseFilename}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=assets\register_full_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional tasks:"; Flags: unchecked

[Files]
Source: "{#MySourceExePath}"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; Flags: ignoreversion

[Dirs]
Name: "{app}\accounts"; Flags: uninsneveruninstall
Name: "{app}\accounts\with_token"; Flags: uninsneveruninstall
Name: "{app}\accounts\without_token"; Flags: uninsneveruninstall
Name: "{app}\codex_tokens"; Flags: uninsneveruninstall

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Run {#MyAppName}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
