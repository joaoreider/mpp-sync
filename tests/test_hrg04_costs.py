"""Validação contra mpp/HRG - 04.mpp (skip se o arquivo ou o Java não existirem)."""

from pathlib import Path

import pytest

HRG04 = Path(__file__).resolve().parents[1] / "mpp" / "HRG - 04.mpp"
BASELINE0_TOTAL = 1_360_295.86


def _parse_hrg04():
    if not HRG04.is_file() or HRG04.stat().st_size < 1000:
        pytest.skip(f"Arquivo de validação ausente: {HRG04}")
    try:
        from project_parser import parse_project_file
    except Exception as exc:
        pytest.skip(f"Parser indisponível: {exc}")
    try:
        return parse_project_file(HRG04)
    except RuntimeError as exc:
        pytest.skip(f"Java/MPXJ indisponível: {exc}")


@pytest.fixture(scope="module")
def hrg04():
    return _parse_hrg04()


def test_hrg04_baseline_zero_sums_to_expected_total(hrg04):
    total = sum(row.custo or 0.0 for row in hrg04.tarefas)
    assert total == pytest.approx(BASELINE0_TOTAL, abs=0.01)


def test_hrg04_every_task_baseline_number_is_zero(hrg04):
    assert hrg04.tarefas
    assert {row.numero_linha_base for row in hrg04.tarefas} == {0}


def test_hrg04_custo_projetado_matches_custo_real_through_status_date(hrg04):
    from org.mpxj.reader import UniversalProjectReader

    from project_parser import _extract_conjunto_dados_faseados

    assert hrg04.status_date is not None
    project = UniversalProjectReader().read(str(HRG04))
    rows = _extract_conjunto_dados_faseados(
        project, hrg04.nome_do_projeto, hrg04.status_date
    )
    mismatches = [
        (row.id_tarefa, row.hora_por_dia, row.custo_projetado, row.custo_real)
        for row in rows
        if row.hora_por_dia <= hrg04.status_date
        and abs(row.custo_projetado - row.custo_real) > 0.01
    ]
    assert mismatches == []


def test_hrg04_projected_cost_is_actual_to_status_plus_remaining(hrg04):
    from org.mpxj.reader import UniversalProjectReader

    from project_parser import _extract_conjunto_dados_faseados

    project = UniversalProjectReader().read(str(HRG04))
    rows = _extract_conjunto_dados_faseados(
        project, hrg04.nome_do_projeto, hrg04.status_date
    )
    projected = sum(row.custo_projetado for row in rows)
    actual_through_status = sum(
        row.custo_real for row in rows if row.hora_por_dia <= hrg04.status_date
    )
    remaining_after_status = sum(
        row.custo_projetado for row in rows if row.hora_por_dia > hrg04.status_date
    )
    assert projected == pytest.approx(
        actual_through_status + remaining_after_status, abs=0.01
    )
    assert remaining_after_status > 0
    actual_total = sum(row.custo_real for row in hrg04.tarefas)
    assert actual_total == pytest.approx(628_914.56, rel=0.01, abs=1.0)
    assert projected == pytest.approx(
        sum(row.custo_projetado for row in hrg04.tarefas), abs=0.01
    )
