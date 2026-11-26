; Instalador de Radar Prop para Windows.
; No instala un navegador propio: crea los accesos "Radar Prop" que abren https://radar-prop.netlify.app
; en una ventana de aplicación de Microsoft Edge (que ya viene con Windows 10/11). Así funciona todo igual
; que en la web (Excel, fichas para imprimir, WhatsApp) y la app se actualiza sola cuando se actualiza la web.
; No pide permisos de administrador: se instala solo para el usuario actual.

#define Nombre "Radar Prop"
#define Url "https://radar-prop.netlify.app/"
#ifndef Version
  #define Version "1.0.0"
#endif

[Setup]
AppId={{8C1E2B54-5F7A-4C1D-9E3B-2A7D6F0B9C41}
AppName={#Nombre}
AppVersion={#Version}
AppPublisher=Guillermo Badenheuer Inmobiliaria
DefaultDirName={localappdata}\Programs\Radar Prop
DefaultGroupName={#Nombre}
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=RadarProp-Instalador
SetupIconFile=radarprop.ico
UninstallDisplayIcon={app}\radarprop.ico
UninstallDisplayName={#Nombre}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso en el escritorio"; GroupDescription: "Accesos:"

[Files]
Source: "radarprop.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#Nombre}"; Filename: "{code:Edge}"; Parameters: "--app={#Url} --no-first-run"; IconFilename: "{app}\radarprop.ico"; AppUserModelID: "Badenheuer.RadarProp"; Comment: "Buscador de propiedades"
Name: "{autodesktop}\{#Nombre}"; Filename: "{code:Edge}"; Parameters: "--app={#Url} --no-first-run"; IconFilename: "{app}\radarprop.ico"; AppUserModelID: "Badenheuer.RadarProp"; Tasks: escritorio

[Run]
Filename: "{code:Edge}"; Parameters: "--app={#Url} --no-first-run"; Description: "Abrir Radar Prop ahora"; Flags: nowait postinstall skipifsilent

[Code]
function Edge(Param: String): String;
var
  Ruta: String;
begin
  Result := '';
  if RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe', '', Ruta) and FileExists(Ruta) then
    Result := Ruta
  else if RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe', '', Ruta) and FileExists(Ruta) then
    Result := Ruta
  else if FileExists(ExpandConstant('{commonpf32}\Microsoft\Edge\Application\msedge.exe')) then
    Result := ExpandConstant('{commonpf32}\Microsoft\Edge\Application\msedge.exe')
  else if FileExists(ExpandConstant('{commonpf64}\Microsoft\Edge\Application\msedge.exe')) then
    Result := ExpandConstant('{commonpf64}\Microsoft\Edge\Application\msedge.exe');
end;

function InitializeSetup(): Boolean;
begin
  Result := Edge('') <> '';
  if not Result then
    MsgBox('Radar Prop necesita Microsoft Edge, que viene con Windows 10 y 11. Instalalo desde microsoft.com/edge y volvé a correr este instalador.', mbError, MB_OK);
end;
