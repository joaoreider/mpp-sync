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

Na primeira execução (ou ao detectar schema legado, inclusive as tabelas
faseadas antigas), o pipeline cria/recria somente `tarefas`. Cada importação
de `.mpp` apaga e reinsere as linhas daquele `nome_do_projeto`.

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
| `hora_por_dia` | HoraPorDia |
| `custo` | Custo (baseline 0 naquele dia) |
| `numero_linha_base` | NúmeroDeLinhaDeBase (sempre 0) |
| `custo_real` | CustoReal |
| `custo_projetado` | CustoProjetado |

Cada linha é um dia da tarefa. No Power BI, `SUM` soma os dias. Não multiplique de novo por dias. Tarefa sem custo próprio fica uma linha com `hora_por_dia` nulo e custos 0.

Valores são **custo próprio** (`FixedCost` + atribuições). Rollup WBS do pai é ignorado. Resumo que **guarda** o custo no próprio FixedCost entra no dia. Baselines 1–10 não são lidas. `numero_linha_base` é sempre 0.

O motor distribui o valor pelos dias úteis (timephased nativo se a soma dos dias estiver a ±1% do total próprio; senão rateio `START` / `END` / `PRORATED`) e grava cada dia em `hora_por_dia`.

- `custo`: custo próprio da baseline 0 (`BaselineFixedCost` + `BaselineCost` das atribuições), rateado nos dias úteis de início e conclusão atuais (`Start`/`Finish`). No `mpp/HRG - 04.mpp` a soma dos dias é **1.360.295,86**.
- `custo_real`: custo próprio reconhecido até o dia da sincronização, nas datas de início e conclusão atuais (`Start`/`Finish`, não a baseline). Na folha, % concluída = dias úteis decorridos ÷ duração, arredondado. No resumo, % = média ponderada pela duração dos filhos. O `ActualCost` gravado no arquivo fica parado na Status Date e não entra na conta. No HRG-04, em 21/09/2026, a soma é **751.973,89** e a tarefa Estaleiro obra é **58.018,18**.
- `custo_projetado`: EAC. Até o dia da sincronização usa o custo real; depois usa o remaining. Sem `BudgetCost`.

Dados já importados só se corrigem **reimportando** o `.mpp`.
