#define MyAppName "MPPSync"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "JP"
#define MyAppExeName "MPPSync.exe"

[Setup]
AppId={{6E3CF36B-1FDE-46D5-A15F-7D0C5E87D3A1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=MPPSync-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Dirs]
Name: "{commonappdata}\{#MyAppName}"; Permissions: users-modify

[Files]
Source: "..\dist\MPPSync\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "runtime\msodbcsql.msi"; DestDir: "{tmp}"; DestName: "msodbcsql.msi"; Flags: deleteafterinstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "msiexec.exe"; Parameters: "/i ""{tmp}\msodbcsql.msi"" /qn IACCEPTMSODBCSQLLICENSETERMS=YES"; StatusMsg: "Instalando ODBC Driver 18 for SQL Server..."; Flags: waituntilterminated
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  DbPage: TInputQueryWizardPage;
  FolderPage: TInputDirWizardPage;

function TrimValue(Value: String): String;
begin
  Result := Trim(Value);
end;

function EnvQuote(Value: String): String;
var
  Escaped: String;
begin
  Escaped := Value;
  StringChangeEx(Escaped, '\', '\\', True);
  StringChangeEx(Escaped, '"', '\"', True);
  Result := '"' + Escaped + '"';
end;

function EnvPath(Value: String): String;
var
  Normalized: String;
begin
  Normalized := Value;
  StringChangeEx(Normalized, '\', '/', True);
  Result := Normalized;
end;

function IsAbsoluteWindowsPath(Value: String): Boolean;
begin
  Result := (Length(Value) >= 3) and (Value[2] = ':') and ((Value[3] = '\') or (Value[3] = '/'));
end;

procedure InitializeWizard;
begin
  DbPage := CreateInputQueryPage(
    wpSelectDir,
    'Configuração do banco',
    'Informe os dados de conexão ODBC.',
    'Esses dados serão salvos em %ProgramData%\MPPSync\.env.'
  );
  DbPage.Add('DSN:', False);
  DbPage.Add('UID:', False);
  DbPage.Add('PWD:', True);
  DbPage.Values[0] := 'PRICIVILRIA';

  FolderPage := CreateInputDirPage(
    DbPage.ID,
    'Pasta monitorada',
    'Escolha a pasta onde os arquivos .mpp serão observados.',
    'O instalador criará a pasta se ela ainda não existir.',
    False,
    ''
  );
  FolderPage.Add('');
  FolderPage.Values[0] := ExpandConstant('{commonappdata}\{#MyAppName}\mpp');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  if CurPageID = DbPage.ID then
  begin
    if TrimValue(DbPage.Values[0]) = '' then
    begin
      MsgBox('Informe o DSN.', mbError, MB_OK);
      Result := False;
      Exit;
    end;

    if TrimValue(DbPage.Values[1]) = '' then
    begin
      MsgBox('Informe o UID.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end;

  if CurPageID = FolderPage.ID then
  begin
    if TrimValue(FolderPage.Values[0]) = '' then
    begin
      MsgBox('Informe a pasta monitorada.', mbError, MB_OK);
      Result := False;
      Exit;
    end;

    if not IsAbsoluteWindowsPath(TrimValue(FolderPage.Values[0])) then
    begin
      MsgBox('Informe um caminho absoluto, por exemplo C:\MPPSync\mpp.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  EnvDir: String;
  EnvFile: String;
  MppDir: String;
  EnvContent: String;
begin
  if CurStep = ssPostInstall then
  begin
    EnvDir := ExpandConstant('{commonappdata}\{#MyAppName}');
    EnvFile := EnvDir + '\.env';
    MppDir := TrimValue(FolderPage.Values[0]);

    ForceDirectories(EnvDir);
    ForceDirectories(MppDir);

    EnvContent :=
      'ODBC_DSN=' + TrimValue(DbPage.Values[0]) + #13#10 +
      'ODBC_UID=' + TrimValue(DbPage.Values[1]) + #13#10 +
      'ODBC_PWD=' + EnvQuote(DbPage.Values[2]) + #13#10 +
      'LOCAL_MPP_DIR=' + EnvPath(MppDir) + #13#10;

    SaveStringToFile(EnvFile, EnvContent, False);
  end;
end;
