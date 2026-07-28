# ETL MS Project MPP

Pipeline para importar arquivos nativos do Microsoft Project (`.mpp`) de uma pasta local para um banco SQL Server acessado via ODBC (DSN).

## Instalando na VM Windows

Use o instalador `MPPSync-Setup.exe`. Ele entrega o app, um JRE portátil para ler `.mpp`, instala o ODBC Driver 18 for SQL Server e cria o `.env` durante a instalação.

O usuário final **não precisa instalar Python nem Inno Setup**. Esses dois itens são usados somente na máquina que gera o instalador. Ao executar o setup, o Windows pedirá permissão de administrador (UAC) para instalar o driver ODBC e gravar os arquivos do app.

1. Execute `MPPSync-Setup.exe` como administrador.
2. Preencha os campos do instalador:
   - DSN
   - UID
   - PWD
   - Pasta monitorada
3. Conclua a instalação e deixe a opção de abrir o app marcada.

O instalador grava a configuração em:

```powershell
%ProgramData%\MPPSync\.env
```

Exemplo do arquivo gerado:

```env
ODBC_DSN=PRICIVILRIA
ODBC_UID=pquery
ODBC_PWD="sua_senha"
LOCAL_MPP_DIR=C:/MPPSync/mpp
```

O DSN informado precisa existir no ODBC da VM e apontar para o SQL Server correto. O instalador pede o nome do DSN e as credenciais, mas não cria a origem ODBC com servidor/banco.

## Uso

Ao abrir, o app tenta conectar automaticamente usando a configuração gravada pelo instalador. A inicialização junto com o Windows é registrada automaticamente.

A interface permite:

- conectar e desconectar o watcher;
- ver o status, o DSN conectado e a pasta monitorada.

Ao fechar a janela, o app continua rodando na bandeja do sistema. Use o ícone da bandeja para mostrar a janela novamente ou **Sair**, que encerra totalmente o app.

Logs de diagnóstico ficam em:

```powershell
%ProgramData%\MPPSync\mppsync.log
```

## Gerando o instalador

Esta seção é só para a máquina de build. O usuário final não executa estes passos.

O build precisa ser feito em uma máquina Windows. Instale antes:

- Python 3.12+
- Inno Setup 6

Depois execute:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build\build.ps1
```

O script:

- cria um venv de build;
- instala dependências e PyInstaller;
- baixa o JRE Temurin 21;
- baixa o ODBC Driver 18 for SQL Server;
- gera `dist\MPPSync\`;
- gera `dist\MPPSync-Setup.exe`.

## Teste na VM

1. Copie `dist\MPPSync-Setup.exe` para a VM.
2. Instale como administrador.
3. Informe DSN, UID, PWD e pasta monitorada.
4. Abra o app e confira se o status ficou **Conectado**.
5. Copie ou salve um `.mpp` na pasta monitorada.
6. Valide se os dados foram persistidos no banco.

## Desenvolvimento local

Para rodar pelo código:

```powershell
python -m pip install -r requirements.txt
python main.py
```

Nesse modo, o app lê `.env` na raiz do projeto.

## Banco

O banco já pode conter tabelas de outros sistemas. Na primeira execução, este pipeline cria **somente** as tabelas `projetos` e `tarefas` caso ainda não existam.
