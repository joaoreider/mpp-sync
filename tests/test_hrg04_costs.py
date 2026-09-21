"""Validação contra mpp/HRG - 04.mpp (skip se o arquivo ou o Java não existirem)."""

from datetime import date
from pathlib import Path

import pytest

HRG04 = Path(__file__).resolve().parents[1] / "mpp" / "HRG - 04.mpp"
BASELINE0_TOTAL = 1_360_295.86
AS_OF = date(2026, 9, 21)
ACTUAL_THROUGH_AS_OF = 751_973.89
ESTALEIRO_OBRA_ID = 138
ESTALEIRO_OBRA_ACTUAL = 58_018.18


def _parse_hrg04():
    if not HRG04.is_file() or HRG04.stat().st_size < 1000:
        pytest.skip(f"Arquivo de validação ausente: {HRG04}")
    try:
        from project_parser import parse_project_file
    except Exception as exc:
        pytest.skip(f"Parser indisponível: {exc}")
    try:
        return parse_project_file(HRG04, as_of=AS_OF)
    except RuntimeError as exc:
        pytest.skip(f"Java/MPXJ indisponível: {exc}")


@pytest.fixture(scope="module")
def hrg04():
    return _parse_hrg04()


def test_hrg04_baseline_zero_sums_to_expected_total(hrg04):
    total = sum(row.custo or 0.0 for row in hrg04.tarefas)
    assert total == pytest.approx(BASELINE0_TOTAL, abs=0.01)


def test_hrg04_custo_days_follow_start_and_finish(hrg04):
    outside = [
        (row.id_tarefa, row.hora_por_dia, row.data_inicio, row.data_conclusao)
        for row in hrg04.tarefas
        if row.custo
        and (
            row.hora_por_dia is None
            or row.data_inicio is None
            or row.data_conclusao is None
            or row.hora_por_dia < row.data_inicio
            or row.hora_por_dia > row.data_conclusao
        )
    ]
    assert outside == []


def test_hrg04_every_task_baseline_number_is_zero(hrg04):
    assert hrg04.tarefas
    assert {row.numero_linha_base for row in hrg04.tarefas} == {0}


def test_hrg04_cost_rows_keep_hora_por_dia(hrg04):
    cost_rows = [
        row
        for row in hrg04.tarefas
        if row.custo or row.custo_real or row.custo_projetado
    ]
    assert cost_rows
    assert all(row.hora_por_dia is not None for row in cost_rows)
    assert len({row.hora_por_dia for row in cost_rows}) > 1


def test_hrg04_custo_projetado_matches_custo_real_through_as_of(hrg04):
    from org.mpxj.reader import UniversalProjectReader

    from project_parser import _extract_conjunto_dados_faseados

    assert hrg04.as_of == AS_OF
    project = UniversalProjectReader().read(str(HRG04))
    rows = _extract_conjunto_dados_faseados(
        project, hrg04.nome_do_projeto, AS_OF
    )
    mismatches = [
        (row.id_tarefa, row.hora_por_dia, row.custo_projetado, row.custo_real)
        for row in rows
        if row.hora_por_dia <= AS_OF
        and abs(row.custo_projetado - row.custo_real) > 0.01
    ]
    assert mismatches == []


def test_hrg04_estaleiro_obra_actual_matches_project_screen(hrg04):
    total = sum(
        row.custo_real or 0.0
        for row in hrg04.tarefas
        if row.id_tarefa == ESTALEIRO_OBRA_ID
    )
    assert total == pytest.approx(ESTALEIRO_OBRA_ACTUAL, abs=0.01)
    assert all(
        row.hora_por_dia is not None and row.hora_por_dia <= AS_OF
        for row in hrg04.tarefas
        if row.id_tarefa == ESTALEIRO_OBRA_ID and row.custo_real
    )


def test_hrg04_projected_cost_is_actual_to_as_of_plus_remaining(hrg04):
    from org.mpxj.reader import UniversalProjectReader

    from project_parser import _extract_conjunto_dados_faseados

    project = UniversalProjectReader().read(str(HRG04))
    rows = _extract_conjunto_dados_faseados(
        project, hrg04.nome_do_projeto, AS_OF
    )
    projected = sum(row.custo_projetado for row in rows)
    actual_through_as_of = sum(
        row.custo_real for row in rows if row.hora_por_dia <= AS_OF
    )
    remaining_after = sum(
        row.custo_projetado for row in rows if row.hora_por_dia > AS_OF
    )
    assert projected == pytest.approx(actual_through_as_of + remaining_after, abs=0.01)
    assert remaining_after > 0
    actual_total = sum(row.custo_real or 0.0 for row in hrg04.tarefas)
    assert actual_total == pytest.approx(ACTUAL_THROUGH_AS_OF, abs=0.05)
    assert actual_through_as_of == pytest.approx(actual_total, abs=0.05)
    assert projected == pytest.approx(
        sum(row.custo_projetado or 0.0 for row in hrg04.tarefas), abs=0.01
    )
