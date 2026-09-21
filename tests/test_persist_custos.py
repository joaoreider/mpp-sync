"""Persistência dos totais de custo em tarefas."""

from datetime import date

import pytest
from sqlalchemy import inspect

from main import persist_arquivo
from models import Tarefa, _engine_cache, get_engine, get_session_factory, init_db
from project_parser import ArquivoProjetoDTO, TarefaDTO


def _url(path) -> str:
    return f"sqlite:///{path}"


def _tarefa(
    nome_do_projeto: str,
    id_tarefa: int,
    custo: float,
    hora_por_dia: date | None = date(2026, 1, 1),
) -> TarefaDTO:
    return TarefaDTO(
        nome_do_projeto=nome_do_projeto,
        id_tarefa=id_tarefa,
        nome_tarefa=f"Tarefa {id_tarefa}",
        data_inicio=None,
        data_conclusao=None,
        desvio_da_conclusao=None,
        duracao_da_tarefa=None,
        duracao_real_da_tarefa=None,
        ordem=id_tarefa,
        spi_da_tarefa=None,
        id_obra=None,
        tarefa_e_resumo=False,
        tarefa_esta_ativa=True,
        wbs_da_tarefa="1",
        hora_por_dia=hora_por_dia,
        custo=custo,
        numero_linha_base=0,
        custo_real=4.25,
        custo_projetado=12.0,
    )


def test_persist_replaces_project_rows_and_keeps_cost_fields(tmp_path):
    url = _url(tmp_path / "persist.db")
    _engine_cache.pop(url, None)
    init_db(url)
    session = get_session_factory(url)()
    persist_arquivo(
        session,
        ArquivoProjetoDTO(
            nome_do_projeto="Obra",
            tarefas=(_tarefa("Obra", 1, 10.5),),
        ),
    )
    session.commit()
    persist_arquivo(
        session,
        ArquivoProjetoDTO(
            nome_do_projeto="Outra",
            tarefas=(_tarefa("Outra", 2, 1.0),),
        ),
    )
    session.commit()
    persist_arquivo(
        session,
        ArquivoProjetoDTO(
            nome_do_projeto="Obra",
            tarefas=(_tarefa("Obra", 1, 20.0),),
        ),
    )
    session.commit()

    obra = session.query(Tarefa).filter(Tarefa.nome_do_projeto == "Obra").all()
    assert len(obra) == 1
    assert obra[0].numero_linha_base == 0
    assert obra[0].hora_por_dia == date(2026, 1, 1)
    assert float(obra[0].custo) == pytest.approx(20.0)
    assert float(obra[0].custo_real) == pytest.approx(4.25)
    assert float(obra[0].custo_projetado) == pytest.approx(12.0)
    assert session.query(Tarefa).filter(Tarefa.nome_do_projeto == "Outra").count() == 1
    session.close()


def test_persist_does_not_create_timephased_tables(tmp_path):
    url = _url(tmp_path / "tables.db")
    _engine_cache.pop(url, None)
    init_db(url)
    session = get_session_factory(url)()
    persist_arquivo(
        session,
        ArquivoProjetoDTO(
            nome_do_projeto="Obra",
            tarefas=(
                _tarefa("Obra", 1, 10.5, date(2026, 1, 1)),
                _tarefa("Obra", 1, 3.0, date(2026, 1, 2)),
            ),
        ),
    )
    session.commit()
    rows = session.query(Tarefa).filter(Tarefa.nome_do_projeto == "Obra").all()
    session.close()
    assert {row.hora_por_dia for row in rows} == {
        date(2026, 1, 1),
        date(2026, 1, 2),
    }

    tables = set(inspect(get_engine(url)).get_table_names())
    assert "conjunto_dados_faseados_tarefa" not in tables
    assert "linhas_base_faseadas_tarefa" not in tables
    assert "tarefas" in tables
