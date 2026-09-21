"""Agregação dos custos diários no total da tarefa."""

from datetime import date

from project_parser import (
    ArquivoProjetoDTO,
    _BaselineDia,
    _CustoDia,
    _cost_totals_by_task,
    costs_or_zero,
)


def test_cost_totals_sum_baseline_zero_only():
    faseados = (
        _CustoDia(
            id_tarefa=1,
            hora_por_dia=date(2026, 1, 1),
            custo_projetado=5.0,
            custo_real=5.0,
        ),
        _CustoDia(
            id_tarefa=1,
            hora_por_dia=date(2026, 1, 2),
            custo_projetado=3.0,
            custo_real=0.0,
        ),
    )
    baselines = (
        _BaselineDia(
            id_tarefa=1,
            hora_por_dia=date(2026, 1, 1),
            numero_linha_base=0,
            custo=10.0,
        ),
        _BaselineDia(
            id_tarefa=1,
            hora_por_dia=date(2026, 1, 2),
            numero_linha_base=0,
            custo=2.0,
        ),
        _BaselineDia(
            id_tarefa=1,
            hora_por_dia=date(2026, 1, 1),
            numero_linha_base=1,
            custo=99.0,
        ),
    )
    assert _cost_totals_by_task(faseados, baselines)[1] == (12.0, 5.0, 8.0)


def test_costs_or_zero_for_missing_task():
    assert costs_or_zero({}, 7) == (0.0, 0.0, 0.0)
    assert not hasattr(
        ArquivoProjetoDTO(nome_do_projeto="x", tarefas=()),
        "conjunto_dados_faseados",
    )
    assert not hasattr(
        ArquivoProjetoDTO(nome_do_projeto="x", tarefas=()),
        "linhas_base_faseadas",
    )
