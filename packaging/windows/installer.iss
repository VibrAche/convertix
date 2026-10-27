; Installeur Windows (Inno Setup 6) — installation par utilisateur, sans droits administrateur.
; Compilation : iscc /DMyAppVersion=0.1.0 packaging\windows\installer.iss
; Prérequis : dist\Convertix\ produit par PyInstaller.

#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#define MyAppName "Convertix"
#define MyAppExe "Convertix.exe"

[Setup]
AppId={{6F0B6C1E-9C1B-4E5D-9F3A-2C7D4B8E1A55}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Enzo Aumaitre
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=Convertix-Setup-{#MyAppVersion}
SetupIconFile=..\..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer une icône sur le Bureau"; Flags: unchecked

[Files]
Source: "..\..\dist\Convertix\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
; Clic droit + « Envoyer vers » + démarrage automatique (tout dans HKCU)
Filename: "{app}\{#MyAppExe}"; Parameters: "--install"; Flags: runhidden waituntilterminated; StatusMsg: "Ajout au menu clic droit…"
Filename: "{app}\{#MyAppExe}"; Parameters: "--tray"; Description: "Lancer Convertix maintenant"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/IM {#MyAppExe} /F"; Flags: runhidden; RunOnceId: "KillApp"
Filename: "{app}\{#MyAppExe}"; Parameters: "--uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "Unregister"

[InstallDelete]
; anciennes versions : on repart d'un dossier propre (évite des DLL orphelines)
Type: filesandordirs; Name: "{app}\_internal"
