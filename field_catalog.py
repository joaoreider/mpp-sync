"""Única fonte de verdade das colunas de custo da tarefa.

Abra este arquivo para ver de onde cada coluna vem e como é calculada.
Para mudar a regra, altere o spec e a função apontada em `mpp_java.py` /
`cost_engine.py`. Cada linha de `tarefas` é um dia (`hora_por_dia`); o total
da tarefa é a soma dessas linhas.

`custo` usa as datas da baseline. `custo_real` e `custo_projetado` usam
os dias úteis entre Start e Finish. O rateio segue o acúmulo START/END/PRORATED.
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
        "Custo real próprio no dia de hora_por_dia, reconhecido até a data "
        "da sincronização. O valor da tarefa é o custo próprio (FixedCost + "
        "atribuições, sem rollup WBS) vezes o % concluído até esse dia. Na "
        "folha o % é o arredondamento de dias úteis decorridos / duração "
        "entre Start e Finish. No resumo o % é a média ponderada pela "
        "duração dos filhos. O valor fica só nos dias úteis até a data; "
        "o campo ActualCost gravado no .mpp não é usado, porque fica parado "
        "na Status Date."
    ),
    eixo_datas=EIXO_CRONOGRAMA_ATUAL,
    total_proprio="cost_engine.accrued_amount",
    timephased_nativo="não usa o timephased gravado; o total segue o % até a data",
    fallback=(
        "rateio do valor reconhecido pelos dias úteis de Start até a data, "
        "conforme FixedCostAccrual (START no primeiro dia, END no último, "
        "PRORATED dividido nos dias decorridos)"
    ),
    estrategia=ESTRATEGIA_NATIVO_OU_RATEIO,
)

CAMPO_CUSTO_REMAINING = CampoCustoFaseado(
    coluna_sql="",
    equivalente_power_bi="",
    tabela_sql="",
    descricao=(
        "Série interna, não persistida. Remaining próprio = custo próprio "
        "menos o custo real reconhecido até a data da sincronização. "
        "Entra em custo_projetado nos dias depois dessa data."
    ),
    eixo_datas=EIXO_CRONOGRAMA_ATUAL,
    total_proprio="custo próprio − custo real reconhecido",
    timephased_nativo="não usa o timephased gravado; remaining = custo próprio − real",
    fallback=(
        "rateio por dias úteis depois da data da sincronização até Finish, "
        "conforme FixedCostAccrual"
    ),
    estrategia=ESTRATEGIA_NATIVO_OU_RATEIO,
)

CAMPO_CUSTO_TAREFA = CampoCustoFaseado(
    coluna_sql="custo_projetado",
    equivalente_power_bi="CustoProjetado",
    tabela_sql="tarefas",
    descricao=(
        "Custo projetado (EAC) no dia de hora_por_dia. Até a data da "
        "sincronização copia o custo real; nos dias seguintes usa o "
        "remaining. Não inclui BudgetCost."
    ),
    eixo_datas=EIXO_HIBRIDO_STATUS,
    total_proprio=(
        "custo real próprio até a data da sincronização + remaining depois"
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
