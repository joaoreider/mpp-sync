# Custos na tarefa Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: skipped — agregar a série diária já existente e gravar o total em `tarefas`
**Status**: Approved

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec - confirm before Execute. Guidelines found: none - strong defaults applied. Test command from `README.md` (`pytest`) and `requirements-dev.txt` (`pytest>=8`). No lint or coverage gate in the repo.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| Schema (`models.py`) | unit | Fresh database creates only `tarefas` with the four columns; legacy timephased tables are dropped | `tests/test_schema_custos.py` | `pytest tests/test_schema_custos.py -q` |
| Parser totals | unit | 1:1 to CUST-01..CUST-07 and the listed aggregation edge cases; HRG-04 totals when the file exists | `tests/test_cost_totals.py`, `tests/test_hrg04_costs.py` | `pytest tests/test_cost_totals.py tests/test_hrg04_costs.py -q` |
| Persistence | integration | Replace-by-project writes the four cost fields and does not recreate timephased tables | `tests/test_persist_custos.py` | `pytest tests/test_persist_custos.py -q` |
| Catalog | unit | Persisted column set is `custo`, `custo_real`, `custo_projetado` on `tarefas` | `tests/test_cost_engine.py` | `pytest tests/test_cost_engine.py -q` |
| Docs | none | build gate only | `README.md` | `pytest -q` |

## Gate Check Commands

> Generated from codebase - confirm before Execute.

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | After tasks with unit tests only | `pytest tests/test_cost_engine.py tests/test_updater.py tests/test_schema_custos.py tests/test_cost_totals.py tests/test_hrg04_costs.py -q` |
| Full | After tasks with integration tests | `pytest -q` |
| Build | After phase completion or docs-only tasks | `pytest -q` |

---

## Execution Plan

Phases are ordered and run sequentially. This feature is one phase (5 tasks), inside a single batch.

### Phase 1: Custos na tarefa

```
T1 -> T2 -> T3 -> T4 -> T5
```

---

## Task Breakdown

### T1: Add cost columns and drop timephased tables

**What**: `Tarefa` ganha `custo`, `numero_linha_base`, `custo_real` e `custo_projetado`; as classes das tabelas faseadas saem; `init_db` recria só `tarefas` quando o schema está defasado.
**Where**: `models.py`
**Depends on**: None
**Reuses**: `_needs_schema_reset` e `_drop_app_tables` em `models.py`
**Requirement**: CUST-08, CUST-09

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `tarefas` tem `custo`, `numero_linha_base`, `custo_real`, `custo_projetado` não nulos
- [x] Banco vazio fica só com `tarefas`
- [x] Tabelas faseadas existentes, ou `tarefas` sem as quatro colunas, disparam drop e recriação
- [x] Gate check passes: `pytest tests/test_schema_custos.py -q`
- [x] Test count: 2 tests pass (no silent deletions)

**Tests**: unit
**Gate**: quick

**Commit**: `feat(tarefas): store cost totals on the task table`

---

### T2: Roll daily series into task totals

**What**: O parser soma a série diária (somente baseline 0) em `TarefaDTO` e deixa de publicar as séries no `ArquivoProjetoDTO`.
**Where**: `project_parser.py`
**Depends on**: T1
**Reuses**: `_extract_conjunto_dados_faseados`, `stitch_hybrid`, `timephased_or_spread`
**Requirement**: CUST-01, CUST-02, CUST-03, CUST-04, CUST-05, CUST-06, CUST-07

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Cada `TarefaDTO` traz os quatro campos; `numero_linha_base` é 0
- [ ] `custo` soma só a baseline 0; baselines 1–10 não entram
- [ ] Tarefa sem custo próprio fica com 0, 0 e 0
- [ ] HRG-04 soma `custo` 1360295.86 e `custo_real` 628914.56
- [ ] A série diária não vai no `ArquivoProjetoDTO`
- [ ] Gate check passes: `pytest tests/test_cost_totals.py tests/test_hrg04_costs.py -q`
- [ ] Test count: 6 tests pass (no silent deletions)

**Tests**: unit
**Gate**: quick

**Commit**: `refactor(parser): roll daily costs into task totals`

---

### T3: Persist only tarefas

**What**: `persist_arquivo` grava os quatro custos em `tarefas` e não escreve mais nas tabelas faseadas.
**Where**: `main.py`
**Depends on**: T2
**Reuses**: `persist_arquivo` e `_delete_by_nome_projeto`
**Requirement**: CUST-10, CUST-11

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] Reimportar o mesmo `nome_do_projeto` substitui a linha e mantém os quatro custos
- [ ] A persistência não cria `conjunto_dados_faseados_tarefa` nem `linhas_base_faseadas_tarefa`
- [ ] Gate check passes: `pytest -q`
- [ ] Test count: full suite passes, with 2 new persist tests (no silent deletions)

**Tests**: integration
**Gate**: full

**Commit**: `refactor(persist): write task cost totals only`

---

### T4: Point the cost catalog at tarefas

**What**: `field_catalog` passa a nomear `custo`, `custo_real` e `custo_projetado` na tabela `tarefas`.
**Where**: `field_catalog.py`
**Depends on**: T3
**Reuses**: `CAMPOS_PERSISTIDOS`
**Requirement**: CUST-05

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `CAMPOS_POR_COLUNA` é exatamente `custo`, `custo_real`, `custo_projetado`
- [ ] Cada campo persistido tem `tabela_sql` igual a `tarefas`
- [ ] Gate check passes: `pytest tests/test_cost_engine.py -q`
- [ ] Test count: 18 tests pass (no silent deletions)

**Tests**: unit
**Gate**: quick

**Commit**: `refactor(catalog): name task-level cost columns`

---

### T5: Document task-level costs

**What**: O README descreve as quatro colunas em `tarefas` e remove as tabelas faseadas e o DAX diário.
**Where**: `README.md`
**Depends on**: T4
**Reuses**: tabela de colunas já existente em `README.md`
**Requirement**: CUST-08

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] O README lista `custo`, `numero_linha_base`, `custo_real` e `custo_projetado` em `tarefas`
- [ ] O README não documenta `conjunto_dados_faseados_tarefa` nem `linhas_base_faseadas_tarefa`
- [ ] Gate check passes: `pytest -q`
- [ ] Test count: full suite passes (no silent deletions)

**Tests**: none
**Gate**: build

**Commit**: `docs(readme): describe task-level cost columns`

---

## Phase Execution Map

```
Phase 1

Phase 1:  T1 -> T2 -> T3 -> T4 -> T5
```

Execution is strictly sequential. Five tasks fit one batch, so Execute runs inline.

---

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1: Add cost columns and drop timephased tables | 1 module | ✅ Granular |
| T2: Roll daily series into task totals | 1 module | ✅ Granular |
| T3: Persist only tarefas | 1 module | ✅ Granular |
| T4: Point the cost catalog at tarefas | 1 module | ✅ Granular |
| T5: Document task-level costs | 1 doc | ✅ Granular |

---

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram Shows | Status |
| ---- | ---------------------- | ------------- | ------ |
| T1 | None | no incoming arrow | ✅ Match |
| T2 | T1 | T1 -> T2 | ✅ Match |
| T3 | T2 | T2 -> T3 | ✅ Match |
| T4 | T3 | T3 -> T4 | ✅ Match |
| T5 | T4 | T4 -> T5 | ✅ Match |

---

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| ---- | --------------------------- | --------------- | --------- | ------ |
| T1: Add cost columns and drop timephased tables | Schema | unit | unit | ✅ OK |
| T2: Roll daily series into task totals | Parser totals | unit | unit | ✅ OK |
| T3: Persist only tarefas | Persistence | integration | integration | ✅ OK |
| T4: Point the cost catalog at tarefas | Catalog | unit | unit | ✅ OK |
| T5: Document task-level costs | Docs | none | none | ✅ OK |
