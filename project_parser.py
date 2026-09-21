"""Leitura de arquivos MS Project (.mpp) para DTOs do pipeline.

Regras de custo: veja `field_catalog.py`. Motor diário: `cost_engine.py`.
Getters MPXJ: `mpp_java.py`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from cost_engine import (
    COST_EPS,
    clip_to_after,
    indices_after,
    stitch_hybrid,
    timephased_or_spread,
)
from field_catalog import (
    CAMPO_CUSTO_LINHA_BASE,
    CAMPO_CUSTO_REAL,
    CAMPO_CUSTO_REMAINING,
    CAMPO_CUSTO_TAREFA,
)
from mpp_java import (
    create_day_ranges,
    day_in_interval,
    days_from_ranges,
    ensure_jvm,
    java_bool,
    java_date,
    java_duration_in_unit,
    java_int,
    java_string,
    mpxj_accrual_kind,
    native_actual_cost,
    native_baseline_cost,
    native_remaining_cost,
    project_nome,
    project_status_date,
    task_accrual_kind,
    task_active,
    task_baseline_accrual_at,
    task_baseline_finish_at,
    task_baseline_start_at,
    task_scalar_actual_cost,
    task_scalar_baseline_cost,
    task_scalar_remaining_cost,
    task_spi,
    to_start_of_day,
    working_indices,
)

logger = logging.getLogger(__name__)

PROJECT_FILE_EXTENSION = ".mpp"

# Índices de baseline do MS Project: 0 = Baseline, 1..10 = Baseline1..Baseline10.
_BASELINE_INDEXES = range(0, 11)


@dataclass(frozen=True, slots=True)
class TarefaDTO:
    """DTO imutável alinhado ao dataset Tarefas do Power BI."""

    nome_do_projeto: str
    id_tarefa: int
    nome_tarefa: str
    data_inicio: date | None
    data_conclusao: date | None
    desvio_da_conclusao: float | None
    duracao_da_tarefa: float | None
    duracao_real_da_tarefa: float | None
    ordem: int | None
    spi_da_tarefa: float | None
    id_obra: str | None
    tarefa_e_resumo: bool | None
    tarefa_esta_ativa: bool | None
    wbs_da_tarefa: str | None


@dataclass(frozen=True, slots=True)
class ConjuntoDadosFaseadosTarefaDTO:
    """DTO do conjunto faseado no tempo (custo / custo real por dia)."""

    nome_do_projeto: str
    id_tarefa: int
    hora_por_dia: date
    custo_tarefa: float | None
    custo_real_da_tarefa: float | None


@dataclass(frozen=True, slots=True)
class LinhaBaseFaseadaTarefaDTO:
    """DTO da linha de base faseada no tempo."""

    nome_do_projeto: str
    id_tarefa: int
    hora_por_dia: date
    numero_linha_base: int
    custo_de_linha_base: float | None


@dataclass(frozen=True, slots=True)
class ArquivoProjetoDTO:
    """Resultado completo da leitura de um arquivo .mpp."""

    nome_do_projeto: str
    tarefas: tuple[TarefaDTO, ...]
    conjunto_dados_faseados: tuple[ConjuntoDadosFaseadosTarefaDTO, ...] = ()
    linhas_base_faseadas: tuple[LinhaBaseFaseadaTarefaDTO, ...] = ()
    status_date: date | None = None


def is_project_file(path: Path) -> bool:
    """Indica se o arquivo tem extensão suportada (.mpp)."""
    return path.suffix.lower() == PROJECT_FILE_EXTENSION


def parse_project_file(path: Path) -> ArquivoProjetoDTO:
    """Parseia um arquivo MS Project nativo."""
    if not is_project_file(path):
        raise ValueError(f"Formato não suportado: {path.suffix}. Use arquivos .mpp.")
    return parse_ms_project_mpp(path)


def _extract_tasks_from_mpp(project, nome_do_projeto: str) -> tuple[TarefaDTO, ...]:
    """Extrai tarefas de um ProjectFile MPXJ."""
    from org.mpxj import TimeUnit

    tarefas: list[TarefaDTO] = []
    for task in project.getTasks():
        uid = java_int(task.getUniqueID())
        if uid is None:
            continue

        nome_tarefa = java_string(task.getName()) or f"Tarefa {uid}"
        wbs = java_string(task.getWBS()) or java_string(task.getOutlineNumber())
        tarefas.append(
            TarefaDTO(
                nome_do_projeto=nome_do_projeto,
                id_tarefa=uid,
                nome_tarefa=nome_tarefa,
                data_inicio=java_date(task.getStart()),
                data_conclusao=java_date(task.getFinish()),
                desvio_da_conclusao=java_duration_in_unit(
                    task.getFinishVariance(), TimeUnit.DAYS
                ),
                duracao_da_tarefa=java_duration_in_unit(
                    task.getDuration(), TimeUnit.DAYS
                ),
                duracao_real_da_tarefa=java_duration_in_unit(
                    task.getActualDuration(), TimeUnit.DAYS
                ),
                ordem=java_int(task.getID()),
                spi_da_tarefa=task_spi(task),
                id_obra=None,
                tarefa_e_resumo=java_bool(task.getSummary()),
                tarefa_esta_ativa=task_active(task),
                wbs_da_tarefa=wbs,
            )
        )

    return tuple(tarefas)


def _actual_working_indices(task, ranges, days: list[date | None], calendar) -> list[int]:
    """Dias úteis do cronograma atual limitados a ActualStart/ActualFinish."""
    start = task.getActualStart() or task.getStart()
    finish = task.getActualFinish() or task.getFinish()
    return [
        index
        for index in working_indices(calendar, ranges)
        if day_in_interval(days[index], start, finish)
    ]


def _extract_conjunto_dados_faseados(
    project, nome_do_projeto: str, status_date: date
) -> tuple[ConjuntoDadosFaseadosTarefaDTO, ...]:
    """Monta custo_real (nativo-ou-rateio) e custo_tarefa (híbrido Status Date)."""
    from org.mpxj.common import TimescaleHelper

    helper = TimescaleHelper()
    rows: list[ConjuntoDadosFaseadosTarefaDTO] = []
    seen: set[tuple[int, date]] = set()
    tasks_with_scalar = 0
    fallback_tasks = 0
    inflated_slices = 0

    for task in project.getTasks():
        uid = java_int(task.getUniqueID())
        if uid is None:
            continue

        start = to_start_of_day(task.getStart())
        finish = to_start_of_day(task.getFinish())
        ranges = create_day_ranges(helper, start, finish)
        if ranges is None:
            continue

        days = days_from_ranges(ranges)
        calendar = task.getEffectiveCalendar()
        accrual = task_accrual_kind(task)
        all_working = working_indices(calendar, ranges)

        scalar_actual = task_scalar_actual_cost(task)
        scalar_remaining = task_scalar_remaining_cost(task)
        if scalar_actual > COST_EPS or scalar_remaining > COST_EPS:
            tasks_with_scalar += 1

        native_actual = native_actual_cost(task, ranges)
        native_remaining = native_remaining_cost(task, ranges)
        actual_indices = _actual_working_indices(task, ranges, days, calendar)

        actuals, used_actual_fallback, actual_inflated = timephased_or_spread(
            native_actual,
            scalar_actual,
            actual_indices,
            accrual,
        )
        remaining, used_remaining_fallback, remaining_inflated = timephased_or_spread(
            clip_to_after(native_remaining, days, status_date),
            scalar_remaining,
            indices_after(days, status_date, all_working),
            accrual,
        )
        costs = stitch_hybrid(days, actuals, remaining, status_date)

        if used_actual_fallback or used_remaining_fallback:
            fallback_tasks += 1
        inflated_slices += int(actual_inflated) + int(remaining_inflated)

        for index, day in enumerate(days):
            custo = costs[index]
            custo_real = actuals[index]
            if custo <= COST_EPS and custo_real <= COST_EPS:
                continue
            if day is None:
                continue
            key = (uid, day)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                ConjuntoDadosFaseadosTarefaDTO(
                    nome_do_projeto=nome_do_projeto,
                    id_tarefa=uid,
                    hora_por_dia=day,
                    custo_tarefa=custo if custo > 0 else 0.0,
                    custo_real_da_tarefa=custo_real if custo_real > 0 else 0.0,
                )
            )

    logger.info(
        "Faseados '%s' (%s = %s até Status Date + remaining; %s): "
        "%d linha(s); %d tarefa(s) com custo próprio; "
        "%d com rateio por dia útil; %d fatia(s) com timephased inflado. "
        "Status Date=%s.",
        nome_do_projeto,
        CAMPO_CUSTO_TAREFA.coluna_sql,
        CAMPO_CUSTO_REAL.coluna_sql,
        CAMPO_CUSTO_REMAINING.total_proprio,
        len(rows),
        tasks_with_scalar,
        fallback_tasks,
        inflated_slices,
        status_date,
    )
    return tuple(rows)


def _extract_linhas_base_faseadas(
    project, nome_do_projeto: str
) -> tuple[LinhaBaseFaseadaTarefaDTO, ...]:
    """Extrai custo_de_linha_base nas datas do plano base (nativo-ou-rateio)."""
    from org.mpxj.common import TimescaleHelper

    helper = TimescaleHelper()
    rows: list[LinhaBaseFaseadaTarefaDTO] = []
    seen: set[tuple[int, date, int]] = set()
    tasks_with_scalar = 0
    fallback_tasks = 0
    inflated_slices = 0

    for task in project.getTasks():
        uid = java_int(task.getUniqueID())
        if uid is None:
            continue

        calendar = task.getEffectiveCalendar()
        used_fallback_for_task = False

        for baseline_number in _BASELINE_INDEXES:
            start = to_start_of_day(task_baseline_start_at(task, baseline_number))
            finish = to_start_of_day(task_baseline_finish_at(task, baseline_number))
            ranges = create_day_ranges(helper, start, finish)
            if ranges is None:
                continue

            scalar = task_scalar_baseline_cost(task, baseline_number)
            if scalar > COST_EPS:
                tasks_with_scalar += 1

            costs, used_fallback, inflated = timephased_or_spread(
                native_baseline_cost(task, baseline_number, ranges),
                scalar,
                working_indices(calendar, ranges),
                mpxj_accrual_kind(task_baseline_accrual_at(task, baseline_number)),
            )
            if used_fallback:
                used_fallback_for_task = True
            if inflated:
                inflated_slices += 1

            for index, day in enumerate(days_from_ranges(ranges)):
                cost_amount = costs[index]
                if cost_amount <= COST_EPS or day is None:
                    continue
                key = (uid, day, baseline_number)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    LinhaBaseFaseadaTarefaDTO(
                        nome_do_projeto=nome_do_projeto,
                        id_tarefa=uid,
                        hora_por_dia=day,
                        numero_linha_base=baseline_number,
                        custo_de_linha_base=cost_amount,
                    )
                )

        if used_fallback_for_task:
            fallback_tasks += 1

    logger.info(
        "Linhas de base faseadas '%s' (%s): %d linha(s); "
        "%d baseline(s) com custo próprio; %d tarefa(s) com rateio por dia útil; "
        "%d fatia(s) com timephased inflado.",
        nome_do_projeto,
        CAMPO_CUSTO_LINHA_BASE.coluna_sql,
        len(rows),
        tasks_with_scalar,
        fallback_tasks,
        inflated_slices,
    )
    return tuple(rows)


def parse_ms_project_mpp(mpp_path: Path) -> ArquivoProjetoDTO:
    """Parseia um arquivo .mpp nativo do MS Project via MPXJ."""
    ensure_jvm()

    from org.mpxj.reader import UniversalProjectReader

    project = UniversalProjectReader().read(str(mpp_path))
    nome_do_projeto = project_nome(project, mpp_path)
    status_date = project_status_date(project)

    return ArquivoProjetoDTO(
        nome_do_projeto=nome_do_projeto,
        tarefas=_extract_tasks_from_mpp(project, nome_do_projeto),
        conjunto_dados_faseados=_extract_conjunto_dados_faseados(
            project, nome_do_projeto, status_date
        ),
        linhas_base_faseadas=_extract_linhas_base_faseadas(project, nome_do_projeto),
        status_date=status_date,
    )
