# Validation: custos-na-tarefa PASS

**Date**: 2026-09-21
**Spec**: `.specs/features/custos-na-tarefa/spec.md`
**Diff range**: ae342b1..007677a
**Verifier**: independent sub-agent (author ≠ verifier)

---

## Task Completion

| Task | Status | Notes |
| ---- | ------ | ----- |
| T1 | ✅ Done | Schema columns and `init_db` reset |
| T2 | ✅ Done | Daily series rolled into task totals |
| T3 | ✅ Done | Persist writes only `tarefas` |
| T4 | ✅ Done | Catalog columns point at `tarefas` |
| T5 | ✅ Done | README lists the four columns and drops the timephased tables |

---

## Spec-Anchored Acceptance Criteria

| Criterion (WHEN X THEN Y) | Spec-defined outcome | `file:line` + assertion | Result |
| ------------------------- | -------------------- | ----------------------- | ------ |
| CUST-01: WHEN um `.mpp` é parseado THEN cada tarefa recebe `custo`, `numero_linha_base`, `custo_real` e `custo_projetado` | Os quatro campos existem em cada tarefa do parse | `tests/test_hrg04_costs.py:31` - `assert total == pytest.approx(BASELINE0_TOTAL, abs=0.01)` with `total = sum(row.custo or 0.0 for row in hrg04.tarefas)`; `tests/test_hrg04_costs.py:36` - `assert {row.numero_linha_base for row in hrg04.tarefas} == {0}`; `tests/test_hrg04_costs.py:79` - `assert actual_total == pytest.approx(628_914.56, rel=0.01, abs=1.0)` with `actual_total = sum(row.custo_real for row in hrg04.tarefas)`; `tests/test_hrg04_costs.py:81` - `assert projected == pytest.approx(sum(row.custo_projetado for row in hrg04.tarefas), abs=0.01)` | ✅ PASS |
| CUST-02: o sistema grava `numero_linha_base` igual a 0 em toda tarefa | Conjunto dos baselines da tarefa é `{0}` | `tests/test_hrg04_costs.py:36` - `assert {row.numero_linha_base for row in hrg04.tarefas} == {0}` | ✅ PASS |
| CUST-03: WHEN a baseline 0 é calculada THEN `custo` é a soma do custo próprio diário dessa baseline e as baselines 1 a 10 ficam de fora | `10.0 + 2.0 = 12.0`; o `99.0` da baseline 1 não entra | `tests/test_cost_totals.py:49` - `assert _cost_totals_by_task(faseados, baselines)[1] == (12.0, 5.0, 8.0)` | ✅ PASS |
| CUST-04: WHEN o custo real é calculado THEN `custo_real` é a soma do custo real próprio diário | `5.0 + 0.0 = 5.0` | `tests/test_cost_totals.py:49` - `assert _cost_totals_by_task(faseados, baselines)[1] == (12.0, 5.0, 8.0)` | ✅ PASS |
| CUST-05: WHEN o custo projetado é calculado THEN `custo_projetado` é a soma da série híbrida (custo real até a Status Date, inclusive, e remaining depois) | Soma sintética `5.0 + 3.0 = 8.0`. No HRG-04, dias `<= status_date` têm `custo_projetado` igual a `custo_real` (diferença máxima 0.01) e a soma das tarefas iguala a soma da série diária | `tests/test_cost_totals.py:49` - `assert _cost_totals_by_task(faseados, baselines)[1] == (12.0, 5.0, 8.0)`; `tests/test_hrg04_costs.py:55` - `assert mismatches == []`; `tests/test_hrg04_costs.py:81` - `assert projected == pytest.approx(sum(row.custo_projetado for row in hrg04.tarefas), abs=0.01)` | ✅ PASS |
| CUST-06: WHEN a tarefa não tem custo próprio THEN `custo`, `custo_real` e `custo_projetado` são 0 | `(0.0, 0.0, 0.0)` para a tarefa ausente | `tests/test_cost_totals.py:53` - `assert costs_or_zero({}, 7) == (0.0, 0.0, 0.0)` | ✅ PASS |
| CUST-07: WHEN `mpp/HRG - 04.mpp` é parseado THEN a soma de `custo` é 1360295.86 (tolerância absoluta 0.01) e a soma de `custo_real` é 628914.56 (tolerância relativa 0.01 e absoluta 1) | `1360295.86` com `abs=0.01`; `628914.56` com `rel=0.01` e `abs=1.0` | `tests/test_hrg04_costs.py:31` - `assert total == pytest.approx(BASELINE0_TOTAL, abs=0.01)` where `BASELINE0_TOTAL = 1_360_295.86` at `tests/test_hrg04_costs.py:8`; `tests/test_hrg04_costs.py:79` - `assert actual_total == pytest.approx(628_914.56, rel=0.01, abs=1.0)` | ✅ PASS |
| CUST-08: WHEN `init_db` roda em banco vazio THEN só existe `tarefas`, com `custo`, `numero_linha_base`, `custo_real` e `custo_projetado` | `tables == {"tarefas"}` e as quatro colunas presentes, não nulas | `tests/test_schema_custos.py:26` - `assert tables == {"tarefas"}`; `tests/test_schema_custos.py:32` - `assert columns[name]["nullable"] is False` for each name in `("custo", "numero_linha_base", "custo_real", "custo_projetado")` | ✅ PASS |
| CUST-09: IF as tabelas faseadas existem, ou IF `tarefas` não tem as quatro colunas, THEN o sistema derruba essas tabelas e recria só `tarefas` | As duas tabelas faseadas somem e `tarefas` volta com as quatro colunas | `tests/test_schema_custos.py:53` - `assert "conjunto_dados_faseados_tarefa" not in tables`; `tests/test_schema_custos.py:54` - `assert "linhas_base_faseadas_tarefa" not in tables`; `tests/test_schema_custos.py:57` - `assert set(_COST_COLUMNS) <= columns` | ✅ PASS |
| CUST-10: WHEN um projeto é persistido THEN o sistema apaga e reinsere só as linhas daquele `nome_do_projeto`, com os quatro campos | Uma linha de "Obra" com `numero_linha_base == 0`, `custo == 20.0`, `custo_real == 4.25`, `custo_projetado == 12.0`; "Outra" permanece com 1 linha | `tests/test_persist_custos.py:69` - `assert len(obra) == 1`; `tests/test_persist_custos.py:70` - `assert obra[0].numero_linha_base == 0`; `tests/test_persist_custos.py:71` - `assert float(obra[0].custo) == pytest.approx(20.0)`; `tests/test_persist_custos.py:72` - `assert float(obra[0].custo_real) == pytest.approx(4.25)`; `tests/test_persist_custos.py:73` - `assert float(obra[0].custo_projetado) == pytest.approx(12.0)`; `tests/test_persist_custos.py:74` - `assert session.query(Tarefa).filter(Tarefa.nome_do_projeto == "Outra").count() == 1` | ✅ PASS |
| CUST-11: o sistema não cria `conjunto_dados_faseados_tarefa` nem `linhas_base_faseadas_tarefa` | Depois de `persist_arquivo`, as duas tabelas estão ausentes e `tarefas` está presente | `tests/test_persist_custos.py:94` - `assert "conjunto_dados_faseados_tarefa" not in tables`; `tests/test_persist_custos.py:95` - `assert "linhas_base_faseadas_tarefa" not in tables`; `tests/test_persist_custos.py:96` - `assert "tarefas" in tables` | ✅ PASS |

**Status**: ✅ All ACs covered

11/11 ACs matched the spec-defined outcome. 0 spec-precision gaps.

---

## Discrimination Sensor

Isolated worktree `/tmp/mpp-sync-custos-sensor` at `007677a`. The real tree was not mutated. `git stash` was not used. Each fault was restored before the next one. The worktree was removed with `git worktree remove --force`.

| Mutation | File:line | Description | Killed? |
| -------- | --------- | ----------- | ------- |
| 1 | `project_parser.py:145` | Removed the baseline filter so baseline 1 (`custo=99.0`) is added into `custo` | ✅ Killed |
| 2 | `project_parser.py:206` | Set `numero_linha_base=1` on every parsed task | ✅ Killed |
| 3 | `models.py:133` | `init_db` no longer calls `_drop_app_tables` | ✅ Killed |

Mutation 1: `tests/test_cost_totals.py:49` failed with `(111.0, 5.0, 8.0) == (12.0, 5.0, 8.0)`. Exit 1.

Mutation 2: `tests/test_hrg04_costs.py:36` failed with `{1} == {0}`. Exit 1. The HRG-04 file was available, so this was a failure, not a skip.

Mutation 3: `tests/test_schema_custos.py:53` failed because `conjunto_dados_faseados_tarefa` was still in the table set. Exit 1.

**Sensor depth**: lightweight
**Result**: 3/3 killed - PASS

`git status --porcelain` after cleanup matched the pre-sensor baseline (`?? .agents/`, `?? .claude/`, `?? .cursor/`, `?? .windsurf/`).

---

## Interactive UAT Results (if performed)

Not performed. The feature is backend persistence and parsing. The automated gate covers it.

---

## Code Quality

| Principle | Status |
| --------- | ------ |
| Minimum code | ✅ |
| Surgical changes | ✅ |
| No scope creep | ✅ |
| Matches patterns | ✅ |
| Spec-anchored outcome check (asserted values match spec) | ✅ |
| Per-layer Coverage Expectation met (domain 1:1 ACs; routes happy+edge+error) | ✅ |
| Every test maps to a spec requirement - no unclaimed tests | ✅ |
| Documented guidelines followed: none - strong defaults applied | ✅ |

Checked against `.cursor/skills/tlc-spec-driven/references/coding-principles.md` and the matrix in `tasks.md`. No routes in scope. Catalog assertion `tests/test_cost_engine.py:139` (`set(CAMPOS_POR_COLUNA) == {"custo", "custo_real", "custo_projetado"}`) and `tests/test_cost_engine.py:146` (`campo.tabela_sql == "tarefas"`) map to the success criterion for `field_catalog.py`. `tests/test_cost_totals.py:54` (`assert not hasattr(..., "conjunto_dados_faseados")`) maps to the T2 done-when that the daily series stays off `ArquivoProjetoDTO`. README lists `custo`, `numero_linha_base`, `custo_real`, and `custo_projetado` and does not document the two timephased tables.

`get_engine` applies `fast_executemany` only for `mssql` URLs. That stays inside the schema task so SQLite `init_db` does not receive SQL Server connect arguments.

---

## Edge Cases

- [x] Agregação não encontra a tarefa: `custo`, `custo_real` e `custo_projetado` são 0, e `numero_linha_base` é 0. `tests/test_cost_totals.py:53` - `assert costs_or_zero({}, 7) == (0.0, 0.0, 0.0)`. `tests/test_hrg04_costs.py:36` - `assert {row.numero_linha_base for row in hrg04.tarefas} == {0}` (o parse inclui tarefas com custo 0).
- [x] Linha diária com `numero_linha_base` diferente de 0 fica fora de `custo`. `tests/test_cost_totals.py:49` - primeiro elemento `12.0`, não `111.0`.
- [x] Banco que já tem as tabelas faseadas perde essas tabelas no `init_db` antes de recriar `tarefas`. `tests/test_schema_custos.py:53` - `assert "conjunto_dados_faseados_tarefa" not in tables`.
- [x] Custo próprio, sem rollup WBS. A soma do HRG-04 permanece 1360295.86. `tests/test_hrg04_costs.py:31` - `assert total == pytest.approx(BASELINE0_TOTAL, abs=0.01)`.

---

## Gate Check

- **Gate command**: `export JAVA_HOME=/home/jp/.local/share/mise/installs/java/temurin-21.0.12+101.0.LTS && /home/jp/projects/mpp-sync/.venv/bin/pytest -q`
- **Result**: 33 passed, 0 failed, 0 skipped
- **Test count before feature**: 26 (`def test_` at `ae342b1`)
- **Test count after feature**: 33 (`def test_` at `007677a`, and the gate collected 33)
- **Delta**: +7 new tests
- **Skipped tests**: none
- **Failures**: none

No test function was deleted. The HRG-04 assertions moved from the timephased rows onto `tarefas` and kept the same tolerances (`abs=0.01` for `custo`, `rel=0.01` and `abs=1.0` for `custo_real`).

---

## Fix Plans (if issues found)

None.

---

## Requirement Traceability Update

Spec statuses were already `Verified` for CUST-01..CUST-11. This report does not edit `spec.md`.

| Requirement | Previous Status | New Status |
| ----------- | --------------- | ---------- |
| CUST-01 | Verified | ✅ Verified |
| CUST-02 | Verified | ✅ Verified |
| CUST-03 | Verified | ✅ Verified |
| CUST-04 | Verified | ✅ Verified |
| CUST-05 | Verified | ✅ Verified |
| CUST-06 | Verified | ✅ Verified |
| CUST-07 | Verified | ✅ Verified |
| CUST-08 | Verified | ✅ Verified |
| CUST-09 | Verified | ✅ Verified |
| CUST-10 | Verified | ✅ Verified |
| CUST-11 | Verified | ✅ Verified |

---

## Summary

**Overall**: ✅ Ready

**Spec-anchored check**: 11/11 ACs matched spec outcome. 0 spec-precision gaps.
**Sensor**: 3/3 mutations killed
**Gate**: 33 passed, 0 failed, 0 skipped

**What works**: Task rows carry baseline-0 `custo`, `numero_linha_base` 0, `custo_real`, and `custo_projetado`. `init_db` leaves only `tarefas`. Persist replaces one project and does not recreate the timephased tables. HRG-04 sums match 1360295.86 and 628914.56.

**Issues found**: none

**Next steps**: none
