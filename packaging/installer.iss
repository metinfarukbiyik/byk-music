; BYK Music – Windows kurulum programı (Inno Setup 6)
; Derleme: iscc /DAppVersion=1.2.3 packaging\installer.iss

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "BYK Music"
#define AppPublisher "biyik.dev"
#define AppDeveloper "Metin Faruk Bıyık"
#define AppURL "https://biyik.dev"
#define RepoURL "https://github.com/metinfarukbiyik/byk-music"
#define AppExe "BYKMusic.exe"

[Setup]
AppId={{8C4E2B1A-5D3F-4A7E-9B6C-2F1E0D9A7B34}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#RepoURL}/issues
AppUpdatesURL={#RepoURL}/releases
AppContact=mb.metinbiyik@gmail.com
AppComments=YouTube MP3 & MP4 İndirici. Geliştirici: {#AppDeveloper} ({#AppPublisher})
AppCopyright=© 2026 {#AppDeveloper} ({#AppPublisher})
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Kurulum Programı
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
VersionInfoCopyright=© 2026 {#AppDeveloper} ({#AppPublisher})
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist-installer
OutputBaseFilename=BYKMusic-Windows-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Güncellemede eski sürümden kalan dosyaları temizle
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\BYKMusic\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "YouTube MP3 & MP4 İndirici"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; Uygulama içinden yapılan sessiz güncellemeden sonra uygulamayı yeniden aç
Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: ShouldRelaunch

[Code]
function ShouldRelaunch: Boolean;
begin
  Result := WizardSilent and (Pos('/NORELAUNCH', UpperCase(GetCmdTail)) = 0);
end;
