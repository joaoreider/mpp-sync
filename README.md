# ETL MS Project MPP

Pipeline para importar arquivos nativos do Microsoft Project (`.mpp`) de uma pasta local para um banco SQL Server acessado via ODBC (DSN).

## Rodando na VM Windows (produção)

1. Configure o DSN de utilizador no **Administrador da Origem de Dados ODBC (64 bits)** e teste a ligação.
2. Instale o [ODBC Driver for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server) se ainda não estiver disponível.
3. Instale as dependências no ambiente Python do projeto:

```powershell
python -m pip install -r requirements.txt
```

4. Configure o `.env` com a connection string que o time passou (use aspas se a senha tiver `#`):

```env
ODBC_CONNECT="DSN=PRICIVILRIA;Uid=pquery;Pwd=sua_senha"
LOCAL_MPP_DIR=C:\caminho\para\mpps
```

Alternativa com variáveis separadas:

```env
ODBC_DSN=PRICIVILRIA
ODBC_UID=pquery
ODBC_PWD="sua_senha"
LOCAL_MPP_DIR=C:\caminho\para\mpps
```

O DSN `PRICIVILRIA` precisa existir no ODBC da VM (User DSN ou System DSN). Se a lista estiver vazia, peça ao time o servidor/banco e crie o DSN antes de rodar o pipeline.

5. Abra a interface gráfica:

```powershell
python main.py
```

A interface permite:

- conectar e desconectar o watcher;
- ver o status, o DSN conectado e a pasta monitorada.

Ao abrir, o app tenta conectar automaticamente usando o `.env`. A inicialização junto com o Windows é registrada automaticamente em toda abertura do app (não há opção para desativar pela interface).

Ao fechar a janela, o app continua rodando na bandeja do sistema. Use o ícone da bandeja para mostrar a janela novamente ou **Sair**, que encerra totalmente o app.

## Banco

O banco já pode conter tabelas de outros sistemas. Na primeira execução, este pipeline cria **somente** as tabelas `projetos` e `tarefas` caso ainda não existam.
