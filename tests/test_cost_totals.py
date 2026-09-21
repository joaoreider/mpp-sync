"""Agregação dos custos diários no total da tarefa."""

from datetime import date

from project_parser import (
    ArquivoProjetoDTO,
    _BaselineDia,
    _CustoDia,
    _days_by_task,
)


def test_days_by_task_keeps_each_day_and_ignores_other_baselines():
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
    assert _days_by_task(faseados, baselines)[1] == (
        (date(2026, 1, 1), 10.0, 5.0, 5.0),
        (date(2026, 1, 2), 2.0, 0.0, 3.0),
    )


def test_arquivo_sem_serie_publica_e_tarefa_sem_dia_fica_de_fora():
    assert _days_by_task((), ()) == {}
    assert not hasattr(
        ArquivoProjetoDTO(nome_do_projeto="x", tarefas=()),
        "conjunto_dados_faseados",
    )
    assert not hasattr(
        ArquivoProjetoDTO(nome_do_projeto="x", tarefas=()),
        "linhas_base_faseadas",
    )
