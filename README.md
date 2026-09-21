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

Ao fechar a janela, o app continua rodando na bandeja do sistema. Use o ícone da bandeja para mostrar a janela novamente, **Atualizar** ou **Sair**.

O botão **Atualizar** (também no tray) consulta os Releases no GitHub, baixa o `MPPSync-Setup.exe` e instala em modo silencioso, preservando o `.env`. O processo antigo é encerrado depois do UAC; o instalador **não** reabre o app (evita duas janelas) — o script de update inicia o exe novo uma vez.

Logs de diagnóstico ficam em:

```powershell
%ProgramData%\MPPSync\mppsync.log
```

## Gerando o instalador (GitHub Actions)

Caminho recomendado: o workflow `.github/workflows/build-installer.yml` gera o instalador no GitHub.

### Release (para baixar na VM)

Na raiz do repo, use o script interativo:

```bash
./update-version.sh
```

Ele pergunta o tipo de incremento (patch/minor/major), a mensagem de commit e notas opcionais do Release; depois atualiza a versão em `updater.py` e `build/installer.iss`, faz commit, push e publica a tag `vX.Y.Z`.

Alternativa manual:

```bash
git tag v1.0.0
git push origin v1.0.0
```

1. Aguarde o workflow **Build installer** concluir.
2. Em **Releases** no GitHub, baixe `MPPSync-Setup.exe`.

### Artifact (sem criar Release)

Em todo push em `main`/`master` (ou via **Actions → Build installer → Run workflow**), o instalador fica disponível como artifact `MPPSync-Setup` na execução do workflow.

### Build local (opcional)

Só se quiser gerar na sua máquina Windows. Instale Python 3.12+ e Inno Setup 6, depois:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build\build.ps1
```

O script cria um venv, baixa JRE/ODBC Driver, gera `dist\MPPSync\` e `dist\MPPSync-Setup.exe`.

## Teste na VM

1. Baixe `MPPSync-Setup.exe` do Release (ou do artifact) e copie para a VM.
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

Testes (pytest + Java para o HRG - 04):

```powershell
python -m pip install -r requirements.txt -r requirements-dev.txt
pytest
```

A pasta `mpp/` pode ter o arquivo local `HRG - 04.mpp` (não versionado). Sem o arquivo ou sem Java, o teste de integração é ignorado. A definição de cada coluna de custo está em `field_catalog.py`; o motor diário em `cost_engine.py`; getters MPXJ em `mpp_java.py`.

## Banco

Na primeira execução (ou ao detectar schema legado), o pipeline cria/recria
três tabelas alinhadas aos datasets do Project Online / Power BI. Cada
importação de `.mpp` apaga e reinsere as linhas daquele `nome_do_projeto`.

### `tarefas` (dataset Tarefas)

| Coluna SQL | Equivalente Power BI |
|---|---|
| `nome_do_projeto` | NomeDoProjeto |
| `id_tarefa` | IdDaTarefa |
| `nome_tarefa` | NomeTarefa |
| `data_inicio` | DataDeInício |
| `data_conclusao` | DataDeConclusão |
| `desvio_da_conclusao` | DesvioDaConclusão |
| `duracao_da_tarefa` | DuraçãoDaTarefa |
| `duracao_real_da_tarefa` | DuraçãoRealDaTarefa |
| `ordem` | Ordem |
| `spi_da_tarefa` | SPIDaTarefa |
| `id_obra` | IdObra (sempre NULL por enquanto) |
| `tarefa_e_resumo` | TarefaÉResumo |
| `tarefa_esta_ativa` | TarefaEstáAtiva |
| `wbs_da_tarefa` | WBSDaTarefa |

### `conjunto_dados_faseados_tarefa` (ConjuntoDeDadosFaseadosNoTempoDaTarefa)

| Coluna SQL | Equivalente Power BI |
|---|---|
| `nome_do_projeto` | (escopo multi-arquivo; não existe no OData) |
| `id_tarefa` | IdDaTarefa |
| `hora_por_dia` | HoraPorDia |
| `custo_tarefa` | CustoTarefa |
| `custo_real_da_tarefa` | CustoRealDaTarefa |

Valores são **custo próprio** (`FixedCost` + atribuições). Rollup WBS do pai é ignorado. Resumo que **guarda** o custo no próprio FixedCost entra na série.

- `custo_real_da_tarefa`: mesmo motor da linha de base, com as datas do cronograma atual (`Start`/`Finish`; fallback em `ActualStart`/`ActualFinish`). Nativo: `getTimephasedActualCost` (+ fixo se não estiver incluído).
- `custo_tarefa`: projetado (EAC). Até a **Status Date** do `.mpp` copia o custo real; depois usa remaining. Sem `BudgetCost`.

Timephased nativo só é usado se a soma dos dias estiver a ±1% do total próprio. Caso contrário (vazio, abaixo demais, inflado, ou só o total — típico de custo fixo de obra), o pipeline rateia pelos **dias úteis** do calendário, conforme o acúmulo (`START`, `END` ou `PRORATED`). Dia com as duas colunas iguais a zero não é gravado.

A coluna já é diária: no Power BI use `SUM`. **Não** multiplique por dias nem use um total de tarefa × `COUNTROWS` do calendário.

Dados já importados só se corrigem **reimportando** o `.mpp` (o watcher substitui as três tabelas daquele `nome_do_projeto`).

### `linhas_base_faseadas_tarefa` (LinhaDeBaseDoConjuntoDeDadosFaseadosNoTempoDaTarefa)

| Coluna SQL | Equivalente Power BI |
|---|---|
| `nome_do_projeto` | (escopo multi-arquivo; não existe no OData) |
| `id_tarefa` | IdDaTarefa |
| `hora_por_dia` | HoraPorDia |
| `numero_linha_base` | NúmeroDeLinhaBase (0 = Baseline, 1..10 = Baseline1..10) |
| `custo_de_linha_base` | CustoDeLinhaDeBase |

A linha de base gravada é **custo próprio** nas datas do plano base (`BaselineStart`/`BaselineFinish`): `BaselineFixedCost` + `BaselineCost` das atribuições. O `BaselineCost` rollup do pai é ignorado; pai sem custo próprio não gera linhas. No `mpp/HRG - 04.mpp`, a soma da baseline 0 é **1.360.295,86**.

A distribuição diária usa `getTimephasedBaselineCost` quando a soma dos dias está a ±1% do total próprio. Se o nativo estiver vazio, abaixo demais, inflado ou só existir o total, o valor é rateado pelos dias úteis. Baseline sem custo próprio não gera linhas (não grava zeros).

No Power BI filtre a baseline corrente e some a coluna diária (nomes SQL; se o modelo usar aliases OData, troque tabela/coluna):

```dax
Custo Linha de Base =
CALCULATE(
    SUM(linhas_base_faseadas_tarefa[custo_de_linha_base]),
    linhas_base_faseadas_tarefa[numero_linha_base] = 0
)
```

A coluna já é diária: **não** multiplique por dias, **não** use `SUMX` de um total de tarefa × `COUNTROWS` do calendário, **não** some `numero_linha_base` 1..10 junto com 0.

Dados já importados só se corrigem **reimportando** o `.mpp`.
