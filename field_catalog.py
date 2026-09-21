"""Única fonte de verdade das colunas de custo da tarefa.

Abra este arquivo para ver de onde cada coluna vem e como é calculada.
Para mudar a regra, altere o spec e a função apontada em `mpp_java.py` /
`cost_engine.py`. Cada linha de `tarefas` é um dia (`hora_por_dia`); o total
da tarefa é a soma dessas linhas.

Motor comum: `cost_engine.timephased_or_spread` (timephased nativo do MPXJ se a
soma dos dias estiver a ±1% do total próprio; senão rateio por dia
útil conforme acúmulo START/END/PRORATED).
"""

from __future__ import annotations

from dataclasses import dataclass

EIXO_BASELINE = "baseline"
EIXO_CRONOGRAMA_ATUAL = "cronograma_atual"
EIXO_HIBRIDO_STATUS = "hibrido_status"

ESTRATEGIA_NATIVO_OU_RATEIO = "nativo_ou_rateio"
ESTRATEGIA_HIBRIDO_STATUS = "hibrido_status"


@dataclass(frozen=True, slots=True)
class CampoCustoFaseado:
    """Descreve uma coluna de custo diário: fonte MPXJ, eixo de datas e fórmula."""

    coluna_sql: str
    equivalente_power_bi: str
    tabela_sql: str
    descricao: str
    eixo_datas: str
    total_proprio: str
    timephased_nativo: str
    fallback: str
    estrategia: str


CAMPO_CUSTO_LINHA_BASE = CampoCustoFaseado(
    coluna_sql="custo",
    equivalente_power_bi="Custo",
    tabela_sql="tarefas",
    descricao=(
        "Custo próprio da baseline 0 no dia de hora_por_dia. "
        "BaselineFixedCost + BaselineCost das atribuições, sem rollup WBS. "
        "Baselines 1..10 não são lidas. Pai sem custo próprio não gera dia."
    ),
    eixo_datas=EIXO_BASELINE,
    total_proprio="mpp_java.task_scalar_baseline_cost",
    timephased_nativo="task.getTimephasedBaselineCost(n, ranges)",
    fallback=(
        "rateio por dias úteis entre BaselineStart e BaselineFinish, "
        "conforme BaselineFixedCostAccrual"
    ),
    estrategia=ESTRATEGIA_NATIVO_OU_RATEIO,
)

CAMPO_CUSTO_REAL = CampoCustoFaseado(
    coluna_sql="custo_real",
    equivalente_power_bi="CustoReal",
    tabela_sql="tarefas",
    descricao=(
        "Custo real próprio no dia de hora_por_dia. A série usa o mesmo motor da "
        "linha de base, com as datas do cronograma atual (Start/Finish; "
        "fallback limitado a ActualStart/ActualFinish). Total = atribuições "
        "ActualCost; se o ActualCost da tarefa couber no teto próprio "
        "(FixedCost + atribuições), usa esse valor (custo fixo apropriado "
        "em folha ou em resumo WBS que guarda o custo). Rollup do pai é "
        "ignorado. Cada dia com valor fica em hora_por_dia."
    ),
    eixo_datas=EIXO_CRONOGRAMA_ATUAL,
    total_proprio="mpp_java.task_scalar_actual_cost",
    timephased_nativo=(
        "getTimephasedActualCost + getTimephasedActualFixedCost "
        "(sem duplicar se o recurso já incluir o fixo)"
    ),
    fallback=(
        "rateio por dias úteis do calendário da tarefa dentro de "
        "ActualStart..ActualFinish (ou Start..Finish se não houver actual), "
        "conforme FixedCostAccrual"
    ),
    estrategia=ESTRATEGIA_NATIVO_OU_RATEIO,
)

CAMPO_CUSTO_REMAINING = CampoCustoFaseado(
    coluna_sql="",
    equivalente_power_bi="",
    tabela_sql="",
    descricao=(
        "Série interna, não persistida. Remaining próprio = "
        "max(atribuições RemainingCost, total próprio − custo real próprio). "
        "Nativo: RemainingCost + RemainingFixedCost. Usada só no stitch de "
        "custo_projetado nos dias depois da Status Date."
    ),
    eixo_datas=EIXO_CRONOGRAMA_ATUAL,
    total_proprio="mpp_java.task_scalar_remaining_cost",
    timephased_nativo=(
        "getTimephasedRemainingCost + getTimephasedRemainingFixedCost "
        "(sem duplicar se o recurso já incluir o fixo)"
    ),
    fallback=(
        "rateio por dias úteis depois da Status Date até Finish, "
        "conforme FixedCostAccrual"
    ),
    estrategia=ESTRATEGIA_NATIVO_OU_RATEIO,
)

CAMPO_CUSTO_TAREFA = CampoCustoFaseado(
    coluna_sql="custo_projetado",
    equivalente_power_bi="CustoProjetado",
    tabela_sql="tarefas",
    descricao=(
        "Custo projetado (EAC) no dia de hora_por_dia. Até a Status Date do "
        ".mpp (ProjectProperties.getStatusDate; se vazia, getCurrentDate; se "
        "ainda vazia, hoje) copia o custo real; nos dias seguintes usa "
        "remaining. Não inclui BudgetCost."
    ),
    eixo_datas=EIXO_HIBRIDO_STATUS,
    total_proprio=(
        "custo real próprio até a Status Date + remaining próprio depois"
    ),
    timephased_nativo="stitch de CAMPO_CUSTO_REAL e CAMPO_CUSTO_REMAINING",
    fallback="cost_engine.stitch_hybrid",
    estrategia=ESTRATEGIA_HIBRIDO_STATUS,
)

CAMPOS_PERSISTIDOS: tuple[CampoCustoFaseado, ...] = (
    CAMPO_CUSTO_LINHA_BASE,
    CAMPO_CUSTO_REAL,
    CAMPO_CUSTO_TAREFA,
)

CAMPOS_POR_COLUNA: dict[str, CampoCustoFaseado] = {
    campo.coluna_sql: campo for campo in CAMPOS_PERSISTIDOS
}
