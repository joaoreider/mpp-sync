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
    accrued_amount,
    integer_percent,
    spread_amount,
    stitch_hybrid,
    timephased_or_spread,
)
from field_catalog import (
    CAMPO_CUSTO_LINHA_BASE,
    CAMPO_CUSTO_REAL,
    CAMPO_CUSTO_TAREFA,
)
from mpp_java import (
    create_day_ranges,
    days_from_ranges,
    ensure_jvm,
    java_bool,
    java_date,
    java_duration_in_unit,
    java_int,
    java_string,
    mpxj_accrual_kind,
    native_baseline_cost,
    numeric_amount,
    project_nome,
    project_status_date,
    task_accrual_kind,
    task_active,
    task_baseline_accrual_at,
    task_baseline_finish_at,
    task_baseline_start_at,
    task_scalar_baseline_cost,
    task_scalar_cost,
    task_spi,
    to_start_of_day,
    working_indices,
)

logger = logging.getLogger(__name__)

PROJECT_FILE_EXTENSION = ".mpp"

# Só a baseline corrente entra no total da tarefa.
_BASELINE_NUMERO = 0


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
    hora_por_dia: date | None = None
    custo: float = 0.0
    numero_linha_base: int = 0
    custo_real: float = 0.0
    custo_projetado: float = 0.0


@dataclass(frozen=True, slots=True)
class _CustoDia:
    """Série diária em memória: real e projetado. Não é persistida."""

    id_tarefa: int
    hora_por_dia: date
    custo_projetado: float
    custo_real: float


@dataclass(frozen=True, slots=True)
class _BaselineDia:
    """Série diária em memória da baseline. Não é persistida."""

    id_tarefa: int
    hora_por_dia: date
    numero_linha_base: int
    custo: float


@dataclass(frozen=True, slots=True)
class ArquivoProjetoDTO:
    """Resultado completo da leitura de um arquivo .mpp."""

    nome_do_projeto: str
    tarefas: tuple[TarefaDTO, ...]
    status_date: date | None = None
    as_of: date | None = None


def is_project_file(path: Path) -> bool:
    """Indica se o arquivo tem extensão suportada (.mpp)."""
    return path.suffix.lower() == PROJECT_FILE_EXTENSION


def parse_project_file(path: Path, *, as_of: date | None = None) -> ArquivoProjetoDTO:
    """Parseia um arquivo MS Project nativo.

    `as_of` é o dia até o qual o custo real é reconhecido. Sem valor, usa
    a data da sincronização (hoje).
    """
    if not is_project_file(path):
        raise ValueError(f"Formato não suportado: {path.suffix}. Use arquivos .mpp.")
    return parse_ms_project_mpp(path, as_of=as_of)


def _days_by_task(
    faseados: tuple[_CustoDia, ...],
    baselines: tuple[_BaselineDia, ...],
) -> dict[int, tuple[tuple[date, float, float, float], ...]]:
    """id_tarefa -> dias (hora_por_dia, custo, custo_real, custo_projetado).

    Baseline diferente de 0 não entra.
    """
    custo: dict[tuple[int, date], float] = {}
    custo_real: dict[tuple[int, date], float] = {}
    custo_projetado: dict[tuple[int, date], float] = {}
    for row in baselines:
        if row.numero_linha_base != _BASELINE_NUMERO:
            continue
        key = (row.id_tarefa, row.hora_por_dia)
        custo[key] = custo.get(key, 0.0) + row.custo
    for row in faseados:
        key = (row.id_tarefa, row.hora_por_dia)
        custo_real[key] = custo_real.get(key, 0.0) + row.custo_real
        custo_projetado[key] = (
            custo_projetado.get(key, 0.0) + row.custo_projetado
        )
    grouped: dict[int, list[tuple[date, float, float, float]]] = {}
    for id_tarefa, day in set(custo) | set(custo_real) | set(custo_projetado):
        grouped.setdefault(id_tarefa, []).append(
            (
                day,
                custo.get((id_tarefa, day), 0.0),
                custo_real.get((id_tarefa, day), 0.0),
                custo_projetado.get((id_tarefa, day), 0.0),
            )
        )
    return {
        id_tarefa: tuple(sorted(days, key=lambda item: item[0]))
        for id_tarefa, days in grouped.items()
    }


def _extract_tasks_from_mpp(
    project,
    nome_do_projeto: str,
    days_by_task: dict[int, tuple[tuple[date, float, float, float], ...]],
) -> tuple[TarefaDTO, ...]:
    """Extrai tarefas de um ProjectFile MPXJ."""
    from org.mpxj import TimeUnit

    tarefas: list[TarefaDTO] = []
    for task in project.getTasks():
        uid = java_int(task.getUniqueID())
        if uid is None:
            continue

        nome_tarefa = java_string(task.getName()) or f"Tarefa {uid}"
        wbs = java_string(task.getWBS()) or java_string(task.getOutlineNumber())
        days = days_by_task.get(uid, ())
        if not days:
            days = ((None, 0.0, 0.0, 0.0),)
        for hora_por_dia, custo, custo_real, custo_projetado in days:
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
                    hora_por_dia=hora_por_dia,
                    custo=custo,
                    numero_linha_base=_BASELINE_NUMERO,
                    custo_real=custo_real,
                    custo_projetado=custo_projetado,
                )
            )

    return tuple(tarefas)


def _elapsed_working_days(work_days: list[date], as_of: date) -> int:
    """Dias úteis de início até `as_of`, inclusive, dentro da duração da tarefa."""
    if not work_days or as_of < work_days[0]:
        return 0
    if as_of >= work_days[-1]:
        return len(work_days)
    return sum(1 for day in work_days if day <= as_of)


def _progress_percents(records: dict[int, dict], as_of: date) -> dict[int, float]:
    """% concluído até `as_of`.

    Folha: dias úteis decorridos / duração, arredondado ao inteiro.
    Resumo: média ponderada pela duração dos filhos imediatos.
    """
    memo: dict[int, float] = {}

    def percent(uid: int) -> float:
        if uid in memo:
            return memo[uid]
        record = records[uid]
        children = record["kids"]
        if not children:
            value = integer_percent(
                _elapsed_working_days(record["work"], as_of), len(record["work"])
            )
        else:
            weighted = 0.0
            weight_total = 0.0
            for child_id in children:
                child = records[child_id]
                weight = child["duration"] if child["duration"] > 0 else float(len(child["work"]))
                weight_total += weight
                weighted += percent(child_id) * weight
            if weight_total <= 0:
                value = integer_percent(
                    _elapsed_working_days(record["work"], as_of), len(record["work"])
                )
            else:
                value = weighted / weight_total
        memo[uid] = value
        return value

    for uid in records:
        percent(uid)
    return memo


def _extract_conjunto_dados_faseados(
    project, nome_do_projeto: str, as_of: date
) -> tuple[_CustoDia, ...]:
    """Custo real até `as_of` nas datas de início/conclusão, e projetado depois."""
    from org.mpxj.common import TimescaleHelper

    helper = TimescaleHelper()
    records: dict[int, dict] = {}

    for task in project.getTasks():
        uid = java_int(task.getUniqueID())
        if uid is None:
            continue
        start = to_start_of_day(task.getStart())
        finish = to_start_of_day(task.getFinish())
        ranges = create_day_ranges(helper, start, finish)
        days = days_from_ranges(ranges) if ranges is not None else []
        working = working_indices(task.getEffectiveCalendar(), ranges) if ranges is not None else []
        work_days = [days[index] for index in working if days[index] is not None]
        kids: list[int] = []
        children = task.getChildTasks()
        if children:
            for child in children:
                child_id = java_int(child.getUniqueID())
                if child_id is not None and child_id != uid:
                    kids.append(child_id)
        records[uid] = {
            "days": days,
            "working": working,
            "work": work_days,
            "kids": kids,
            "duration": numeric_amount(task.getDuration()),
            "scalar": task_scalar_cost(task),
            "accrual": task_accrual_kind(task),
        }

    percents = _progress_percents(records, as_of)
    rows: list[_CustoDia] = []
    seen: set[tuple[int, date]] = set()
    tasks_with_scalar = 0

    for uid, record in records.items():
        scalar = record["scalar"]
        if scalar <= COST_EPS:
            continue
        tasks_with_scalar += 1
        days: list[date | None] = record["days"]
        working: list[int] = record["working"]
        if not days or not working:
            continue

        percent = percents[uid]
        accrued = accrued_amount(scalar, percent, record["accrual"])
        remaining = max(0.0, scalar - accrued)
        elapsed_indices = [
            index
            for index in working
            if days[index] is not None and days[index] <= as_of
        ]
        future_indices = [
            index
            for index in working
            if days[index] is not None and days[index] > as_of
        ]
        if accrued > COST_EPS and not elapsed_indices:
            elapsed_indices = [working[0]]
        actuals = spread_amount(accrued, elapsed_indices, record["accrual"], len(days))
        if remaining > COST_EPS and not future_indices:
            projected_remaining = [0.0] * len(days)
            projected_remaining[working[-1]] = remaining
            costs = [
                actual + extra
                for actual, extra in zip(actuals, projected_remaining, strict=True)
            ]
        else:
            remaining_series = spread_amount(
                remaining, future_indices, record["accrual"], len(days)
            )
            costs = stitch_hybrid(days, actuals, remaining_series, as_of)

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
                _CustoDia(
                    id_tarefa=uid,
                    hora_por_dia=day,
                    custo_projetado=custo if custo > 0 else 0.0,
                    custo_real=custo_real if custo_real > 0 else 0.0,
                )
            )

    logger.info(
        "Faseados '%s' (%s até %s; %s): %d linha(s); %d tarefa(s) com custo próprio.",
        nome_do_projeto,
        CAMPO_CUSTO_REAL.coluna_sql,
        as_of,
        CAMPO_CUSTO_TAREFA.coluna_sql,
        len(rows),
        tasks_with_scalar,
    )
    return tuple(rows)


def _extract_linhas_base_faseadas(
    project, nome_do_projeto: str
) -> tuple[_BaselineDia, ...]:
    """Extrai o custo da baseline 0 nas datas do plano base (nativo-ou-rateio)."""
    from org.mpxj.common import TimescaleHelper

    helper = TimescaleHelper()
    rows: list[_BaselineDia] = []
    seen: set[tuple[int, date]] = set()
    tasks_with_scalar = 0
    fallback_tasks = 0
    inflated_slices = 0

    for task in project.getTasks():
        uid = java_int(task.getUniqueID())
        if uid is None:
            continue

        calendar = task.getEffectiveCalendar()
        used_fallback_for_task = False

        start = to_start_of_day(task_baseline_start_at(task, _BASELINE_NUMERO))
        finish = to_start_of_day(task_baseline_finish_at(task, _BASELINE_NUMERO))
        ranges = create_day_ranges(helper, start, finish)
        if ranges is None:
            continue

        scalar = task_scalar_baseline_cost(task, _BASELINE_NUMERO)
        if scalar > COST_EPS:
            tasks_with_scalar += 1

        costs, used_fallback, inflated = timephased_or_spread(
            native_baseline_cost(task, _BASELINE_NUMERO, ranges),
            scalar,
            working_indices(calendar, ranges),
            mpxj_accrual_kind(task_baseline_accrual_at(task, _BASELINE_NUMERO)),
        )
        if used_fallback:
            used_fallback_for_task = True
        if inflated:
            inflated_slices += 1

        for index, day in enumerate(days_from_ranges(ranges)):
            cost_amount = costs[index]
            if cost_amount <= COST_EPS or day is None:
                continue
            key = (uid, day)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                _BaselineDia(
                    id_tarefa=uid,
                    hora_por_dia=day,
                    numero_linha_base=_BASELINE_NUMERO,
                    custo=cost_amount,
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


def parse_ms_project_mpp(mpp_path: Path, *, as_of: date | None = None) -> ArquivoProjetoDTO:
    """Parseia um arquivo .mpp nativo do MS Project via MPXJ."""
    ensure_jvm()

    from org.mpxj.reader import UniversalProjectReader

    project = UniversalProjectReader().read(str(mpp_path))
    nome_do_projeto = project_nome(project, mpp_path)
    status_date = project_status_date(project)
    resolved_as_of = as_of or date.today()
    faseados = _extract_conjunto_dados_faseados(
        project, nome_do_projeto, resolved_as_of
    )
    baselines = _extract_linhas_base_faseadas(project, nome_do_projeto)

    return ArquivoProjetoDTO(
        nome_do_projeto=nome_do_projeto,
        tarefas=_extract_tasks_from_mpp(
            project,
            nome_do_projeto,
            _days_by_task(faseados, baselines),
        ),
        status_date=status_date,
        as_of=resolved_as_of,
    )
