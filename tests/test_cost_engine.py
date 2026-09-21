"""Testes do motor de séries diárias (sem JVM)."""

from datetime import date

import pytest

from cost_engine import (
    clip_to_after,
    clip_to_on_or_before,
    combine_resource_and_fixed,
    indices_after,
    own_or_assignment,
    spread_amount,
    stitch_hybrid,
    timephased_or_spread,
)
from field_catalog import CAMPOS_PERSISTIDOS, CAMPOS_POR_COLUNA, CAMPO_CUSTO_TAREFA


def test_spread_start_puts_all_on_first_working_day():
    result = spread_amount(100.0, [1, 3, 5], "START", 7)
    assert result == [0.0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_spread_end_puts_all_on_last_working_day():
    result = spread_amount(100.0, [1, 3, 5], "END", 7)
    assert result == [0.0, 0.0, 0.0, 0.0, 0.0, 100.0, 0.0]


def test_spread_prorated_splits_and_last_day_absorbs_remainder():
    result = spread_amount(100.0, [0, 1, 2], "PRORATED", 3)
    assert result[0] == result[1]
    assert sum(result) == 100.0
    assert result[2] == pytest.approx(100.0 - result[0] - result[1])


def test_spread_zero_or_no_working_days_is_all_zeros():
    assert spread_amount(0.0, [0, 1], "PRORATED", 2) == [0.0, 0.0]
    assert spread_amount(10.0, [], "PRORATED", 2) == [0.0, 0.0]


def test_native_accepted_when_sum_matches_scalar():
    native = [10.0, 20.0, 30.0]
    values, used_fallback, inflated = timephased_or_spread(
        native, 60.0, [0, 1, 2], "PRORATED"
    )
    assert values == native
    assert used_fallback is False
    assert inflated is False


def test_undercount_native_falls_back_to_spread():
    native = [10.0, 0.0, 0.0]
    values, used_fallback, inflated = timephased_or_spread(
        native, 100.0, [0, 1, 2], "PRORATED"
    )
    assert used_fallback is True
    assert inflated is False
    assert sum(values) == pytest.approx(100.0)


def test_empty_native_falls_back_to_spread():
    native = [0.0, 0.0, 0.0]
    values, used_fallback, inflated = timephased_or_spread(
        native, 90.0, [0, 1, 2], "PRORATED"
    )
    assert used_fallback is True
    assert inflated is False
    assert sum(values) == 90.0


def test_inflated_native_is_replaced_by_spread():
    native = [100.0, 100.0, 100.0]
    values, used_fallback, inflated = timephased_or_spread(
        native, 100.0, [0, 1, 2], "PRORATED"
    )
    assert used_fallback is True
    assert inflated is True
    assert sum(values) == 100.0


def test_zero_scalar_zeros_the_series():
    values, used_fallback, inflated = timephased_or_spread(
        [1.0, 2.0], 0.0, [0, 1], "PRORATED"
    )
    assert values == [0.0, 0.0]
    assert used_fallback is False
    assert inflated is False


def test_combine_skips_fixed_already_inside_resource():
    resource = [5.0, 5.0]
    fixed = [5.0, 5.0]
    assert combine_resource_and_fixed(resource, fixed) == resource


def test_combine_adds_when_fixed_is_disjoint():
    resource = [5.0, 0.0]
    fixed = [0.0, 3.0]
    assert combine_resource_and_fixed(resource, fixed) == [5.0, 3.0]


def test_own_or_assignment_keeps_task_amount_inside_cap():
    assert own_or_assignment(80.0, 10.0, 100.0) == 80.0


def test_own_or_assignment_drops_wbs_rollup():
    assert own_or_assignment(500.0, 0.0, 0.0) == 0.0


def test_stitch_hybrid_uses_actual_through_status_date():
    days = [date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10)]
    actual = [10.0, 20.0, 99.0]
    remaining = [1.0, 2.0, 30.0]
    result = stitch_hybrid(days, actual, remaining, date(2026, 9, 9))
    assert result == [10.0, 20.0, 30.0]


def test_indices_after_status_date_are_strict():
    days = [date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10), None]
    assert indices_after(days, date(2026, 9, 9), [0, 1, 2, 3]) == [2]


def test_clip_to_after_zeros_days_through_status_date():
    days = [date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10)]
    assert clip_to_after([1.0, 2.0, 3.0], days, date(2026, 9, 9)) == [0.0, 0.0, 3.0]


def test_clip_to_on_or_before_zeros_days_after_status_date():
    days = [date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10)]
    assert clip_to_on_or_before([1.0, 2.0, 3.0], days, date(2026, 9, 9)) == [
        1.0,
        2.0,
        0.0,
    ]


def test_catalog_persisted_columns_are_unique_and_documented():
    assert set(CAMPOS_POR_COLUNA) == {
        "custo_de_linha_base",
        "custo_real_da_tarefa",
        "custo_tarefa",
    }
    for campo in CAMPOS_PERSISTIDOS:
        assert campo.equivalente_power_bi
        assert campo.tabela_sql
        assert campo.descricao
        assert campo.total_proprio
        assert campo.timephased_nativo
        assert campo.estrategia
    assert CAMPO_CUSTO_TAREFA.estrategia == "hibrido_status"
