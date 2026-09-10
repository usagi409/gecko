#ifndef MyAppVersion
  #define MyAppVersion "dev"
#endif

[Setup]
AppId={{9E4B7F2A-3C5D-4E8F-A6B2-0123456789AB}
AppName=gecko
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\gecko
DefaultGroupName=gecko
OutputDir=Output
OutputBaseFilename=gecko-setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Types]
Name: "full"; Description: "フルインストール"

[Components]
Name: "core"; Description: "gecko 本体（.gek ダブルクリック実行）"; Types: full
Name: "cli";  Description: "gecko コマンドを PATH に追加"; Types: full

[Files]
Source: "dist\gecko\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "sample.gek"; DestDir: "{app}\samples"; Flags: ignoreversion

[Icons]
Name: "{group}\サンプルを開く"; Filename: "{app}\samples\sample.gek"

[Registry]
Root: HKCU; Subkey: "Software\Classes\.gek"; ValueType: string; ValueData: "Gecko.File"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Gecko.File"; ValueType: string; ValueData: "Gecko Japanese Code"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Gecko.File\shell\open\command"; ValueType: string; ValueData: """{app}\gek-click.bat"" ""%1"""; Flags: uninsdeletekey

[Code]
const EnvironmentKey = 'Environment';

procedure EnvAddPath(instlPath: string);
var
  Paths: string;
begin
  if not RegQueryStringValue(HKCU, EnvironmentKey, 'Path', Paths) then
    Paths := '';
  if Pos(';' + Uppercase(instlPath) + ';', ';' + Uppercase(Paths) + ';') > 0 then
    exit;
  if Paths = '' then
    Paths := instlPath
  else
    Paths := Paths + ';' + instlPath;
  RegWriteStringValue(HKCU, EnvironmentKey, 'Path', Paths);
end;

procedure EnvRemovePath(instlPath: string);
var
  Paths: string;
  P: Integer;
begin
  if not RegQueryStringValue(HKCU, EnvironmentKey, 'Path', Paths) then
    exit;
  P := Pos(';' + Uppercase(instlPath) + ';', ';' + Uppercase(Paths) + ';');
  if P = 0 then
    exit;
  if P = 1 then
    Delete(Paths, P, Length(';' + instlPath))
  else
    Delete(Paths, P - 1, Length(';' + instlPath));
  RegWriteStringValue(HKCU, EnvironmentKey, 'Path', Paths);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if IsComponentSelected('cli') then
      EnvAddPath(ExpandConstant('{app}'));
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    EnvRemovePath(ExpandConstant('{app}'));
end;
