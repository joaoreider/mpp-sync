# ETL MS Project MPP

Pipeline para importar arquivos nativos do Microsoft Project (`.mpp`) de uma pasta local para um banco relacional.

## Rodando com Docker

1. Coloque seus arquivos `.mpp` na pasta `mpp/`.
2. Confira o `.env`:

```env
DATABASE_URL=postgresql://postgres:postgres@db:5432/app
LOCAL_MPP_DIR=/data/mpp
```

3. Execute:

```bash
docker compose up --build app
```

O Compose monta a pasta `mpp/` na VM/container e executa o pipeline uma vez.

## Banco

As tabelas `projetos` e `tarefas` são criadas automaticamente na primeira execução.
