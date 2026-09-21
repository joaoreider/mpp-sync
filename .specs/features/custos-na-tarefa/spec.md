# Custos totais em tarefas

## Problem Statement

Os custos do `.mpp` estão em séries diárias (`conjunto_dados_faseados_tarefa` e `linhas_base_faseadas_tarefa`). O consumo em `tarefas` precisa de um total por tarefa, não de uma linha por dia. Baseline 1–10 e `hora_por_dia` não entram mais no banco.

## Goals

- [ ] Cada linha de `tarefas` guarda `custo` (baseline 0), `numero_linha_base` = 0, `custo_real` e `custo_projetado`
- [ ] As tabelas `conjunto_dados_faseados_tarefa` e `linhas_base_faseadas_tarefa` deixam de existir depois do `init_db`
- [ ] No `mpp/HRG - 04.mpp`, a soma de `custo` é 1360295.86 e a soma de `custo_real` é 628914.56 (±1)

## Out of Scope

| Feature | Reason |
| --- | --- |
| Baselines 1–10 | Decisão do usuário: só a baseline 0 é gravada |
| Série diária persistida (`hora_por_dia`) | O grão passa a ser uma linha por tarefa |
| Mudança da fórmula de custo próprio, rateio ou stitch da Status Date | O motor diário continua em memória; só a persistência muda |
| `design.md` | Agregar a série existente e gravar o total não introduz padrão novo |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Grão | Uma linha por `(nome_do_projeto, id_tarefa)`, sem `hora_por_dia` | A tabela `tarefas` já tem essa chave | y |
| Baseline | Só a baseline 0; `numero_linha_base` é sempre 0; baselines 1–10 não são lidas | Usuário escolheu `baseline_0_only` | y |
| Valores sem custo próprio | `custo`, `custo_real` e `custo_projetado` são 0, não NULL | Toda tarefa existe na tabela; zero não altera um `SUM` | y |
| `custo_projetado` | Soma da série híbrida (custo real nos dias até a Status Date + remaining nos dias seguintes), o valor que hoje se chama `custo_tarefa` | O usuário definiu CustoProjetado como o atual custoTarefa | y |
| Reset de schema | Se as tabelas faseadas existirem, ou se `tarefas` não tiver as quatro colunas, `init_db` derruba as tabelas do app e recria só `tarefas` | O pipeline já recria schema defasado e regrava no próximo sync | y |

**Open questions:** none

---

## User Stories

### P1: Totais de custo na tarefa ⭐ MVP

**User Story**: As a consumidor dos dados no banco, I want each task row to carry baseline, actual, and projected cost so that I do not join timephased tables.

**Why P1**: Sem essas colunas o refactor não entrega o dado.

**Acceptance Criteria**:

1. WHEN um arquivo `.mpp` é parseado THEN o sistema SHALL preencher em cada tarefa `custo`, `numero_linha_base`, `custo_real` e `custo_projetado`.
2. The sistema SHALL gravar `numero_linha_base` igual a 0 em toda tarefa.
3. WHEN a baseline 0 é calculada THEN o sistema SHALL definir `custo` como a soma do custo próprio diário dessa baseline para a tarefa, e SHALL ignorar as baselines 1 a 10.
4. WHEN o custo real é calculado THEN o sistema SHALL definir `custo_real` como a soma do custo real próprio diário da tarefa.
5. WHEN o custo projetado é calculado THEN o sistema SHALL definir `custo_projetado` como a soma da série híbrida da tarefa (custo real em cada dia até a Status Date, inclusive, e remaining em cada dia posterior).
6. WHEN a tarefa não tem custo próprio THEN o sistema SHALL gravar `custo`, `custo_real` e `custo_projetado` iguais a 0.
7. WHEN `mpp/HRG - 04.mpp` é parseado THEN o sistema SHALL produzir soma de `custo` igual a 1360295.86 (tolerância absoluta 0.01) e soma de `custo_real` igual a 628914.56 (tolerância relativa 0.01 e absoluta 1).

**Independent Test**: Parsear o HRG-04 e somar `tarefa.custo` e `tarefa.custo_real`. Um teste de agregação com dias sintéticos prova que a baseline 1 não entra no total e que a tarefa ausente vira zero.

---

### P1: Só a tabela tarefas

**User Story**: As a operador do sync, I want a single `tarefas` table so that old timephased tables are not recreated.

**Why P1**: O pedido é remover as duas tabelas, não só deixar de usá-las.

**Acceptance Criteria**:

1. WHEN `init_db` roda em um banco vazio THEN o sistema SHALL criar somente a tabela `tarefas`, com as colunas `custo`, `numero_linha_base`, `custo_real` e `custo_projetado`.
2. IF `conjunto_dados_faseados_tarefa` ou `linhas_base_faseadas_tarefa` existir, ou IF `tarefas` não tiver as quatro colunas, THEN o sistema SHALL derrubar essas tabelas e recriar somente `tarefas`.
3. WHEN um projeto é persistido THEN o sistema SHALL apagar e reinserir somente as linhas de `tarefas` daquele `nome_do_projeto`, incluindo os quatro campos de custo.
4. The sistema SHALL NOT criar `conjunto_dados_faseados_tarefa` nem `linhas_base_faseadas_tarefa`.

**Independent Test**: SQLite em memória com as tabelas antigas; depois de `init_db` só existe `tarefas` com as colunas novas. `persist_arquivo` grava os quatro valores e uma segunda persistência do mesmo projeto não duplica a linha.

---

## Edge Cases

- WHEN a agregação não encontra a tarefa THEN o sistema SHALL usar 0 para `custo`, `custo_real` e `custo_projetado` e 0 para `numero_linha_base`.
- WHEN uma linha diária de baseline tem `numero_linha_base` diferente de 0 THEN o sistema SHALL excluir esse valor de `custo`.
- IF o banco já tem as tabelas faseadas THEN o sistema SHALL removê-las no `init_db` antes de recriar `tarefas`.
- The sistema SHALL manter o custo próprio (sem rollup WBS). A soma do HRG-04 continua 1360295.86, que é o total próprio da baseline 0, não o rollup.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| CUST-01 | P1: Totais de custo na tarefa | T2 | Verified |
| CUST-02 | P1: Totais de custo na tarefa | T2 | Verified |
| CUST-03 | P1: Totais de custo na tarefa | T2 | Verified |
| CUST-04 | P1: Totais de custo na tarefa | T2 | Verified |
| CUST-05 | P1: Totais de custo na tarefa | T2 | Verified |
| CUST-06 | P1: Totais de custo na tarefa | T2 | Verified |
| CUST-07 | P1: Totais de custo na tarefa | T2 | Verified |
| CUST-08 | P1: Só a tabela tarefas | T1 | Verified |
| CUST-09 | P1: Só a tabela tarefas | T1 | Verified |
| CUST-10 | P1: Só a tabela tarefas | T3 | Verified |
| CUST-11 | P1: Só a tabela tarefas | T3 | Verified |

**Coverage:** 11 total, 11 mapped to tasks, 0 unmapped

---

## Success Criteria

- [ ] `pytest` passa, incluindo o total 1360295.86 e 628914.56 no HRG-04 quando o arquivo e o Java existem
- [ ] `init_db` não recria as duas tabelas faseadas
- [ ] `field_catalog.py` e o README descrevem `custo`, `custo_real` e `custo_projetado` em `tarefas`
