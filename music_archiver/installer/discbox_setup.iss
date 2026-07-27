; Script do Inno Setup para o instalador do DISCBOX.
; Gera Setup.exe a partir do executável já compilado em dist\DISCBOX.exe
; (rode scripts\build_windows.ps1 antes disso).
;
; Uso: "ISCC.exe installer\discbox_setup.iss"
; (ou abra este arquivo no Inno Setup Compiler e clique em Compilar)

#define MyAppName "DISCBOX"
#define MyAppVersion "1.0.0"
#define MyAppExeName "DISCBOX.exe"
#define MyAppLinkedIn "https://www.linkedin.com/in/joao-carvalho21/"

[Setup]
AppId={{6C7C2E6E-6C6B-4A6E-9C7A-DISCBOX00001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=DISCBOX-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

; Tela simples: só boas-vindas -> instalar -> concluir (com opção de abrir o
; app e/ou visitar o LinkedIn do desenvolvedor). Sem tela de "escolher pasta"
; nem "grupo do menu iniciar", pra ser rápido.
DisableWelcomePage=no
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableFinishedPage=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos adicionais:"

[Files]
Source: "..\dist\DISCBOX.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir o {#MyAppName} agora"; Flags: nowait postinstall skipifsilent
Filename: "{#MyAppLinkedIn}"; Description: "Visitar meu LinkedIn"; Flags: postinstall shellexec skipifsilent unchecked
