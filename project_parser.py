"""Leitura de arquivos MS Project (.mpp) para DTOs do pipeline."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_FILE_EXTENSION = ".mpp"

# Índices de baseline do MS Project: 0 = Baseline, 1..10 = Baseline1..Baseline10.
_BASELINE_INDEXES = range(0, 11)
_COST_EPS = 1e-9
_NATIVE_INFLATE_RATIO = 1.01
_NATIVE_INFLATE_ABS = 0.01


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


def is_project_file(path: Path) -> bool:
    """Indica se o arquivo tem extensão suportada (.mpp)."""
    return path.suffix.lower() == PROJECT_FILE_EXTENSION


def parse_project_file(path: Path) -> ArquivoProjetoDTO:
    """Parseia um arquivo MS Project nativo."""
    if not is_project_file(path):
        raise ValueError(f"Formato não suportado: {path.suffix}. Use arquivos .mpp.")
    return parse_ms_project_mpp(path)


_jvm_started = False


def _ensure_jvm() -> None:
    """Inicia a JVM para leitura de arquivos .mpp via MPXJ."""
    global _jvm_started
    if _jvm_started:
        return

    import jpype
    import mpxj  # noqa: F401 - registra JARs do MPXJ no classpath

    if not jpype.isJVMStarted():
        try:
            bundled_jvm = _bundled_jvm_path()
            if bundled_jvm is not None:
                jpype.startJVM(str(bundled_jvm))
            else:
                jpype.startJVM()
        except jpype.JVMNotFoundException as exc:
            raise RuntimeError(
                "Leitura de .mpp requer Java. O instalador inclui um JRE; "
                "reinstale o app se esse erro aparecer na VM."
            ) from exc

    _jvm_started = True


def _bundled_jvm_path() -> Path | None:
    """Retorna a JVM do JRE empacotado pelo instalador Windows."""
    if not getattr(sys, "frozen", False):
        return None

    app_dir = Path(sys.executable).resolve().parent
    jvm_dll = app_dir / "jre" / "bin" / "server" / "jvm.dll"
    return jvm_dll if jvm_dll.exists() else None


def _java_number(value) -> float | None:
    """Converte tipos numéricos Java em float Python."""
    if value is None:
        return None
    if hasattr(value, "doubleValue"):
        return float(value.doubleValue())
    return float(value)


def _java_string(value) -> str | None:
    """Converte strings Java em str Python."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _java_int(value) -> int | None:
    """Converte tipos inteiros Java em int Python."""
    if value is None:
        return None
    if hasattr(value, "intValue"):
        return int(value.intValue())
    return int(value)


def _java_bool(value) -> bool | None:
    """Converte Boolean Java em bool Python."""
    if value is None:
        return None
    if hasattr(value, "booleanValue"):
        return bool(value.booleanValue())
    return bool(value)


def _java_date(value) -> date | None:
    """Converte datas Java (LocalDateTime, LocalDate, Date) em date Python."""
    if value is None:
        return None
    if hasattr(value, "toLocalDate"):
        local_date = value.toLocalDate()
        return date(
            int(local_date.getYear()),
            int(local_date.getMonthValue()),
            int(local_date.getDayOfMonth()),
        )
    if hasattr(value, "getYear") and hasattr(value, "getMonthValue"):
        return date(
            int(value.getYear()),
            int(value.getMonthValue()),
            int(value.getDayOfMonth()),
        )
    logger.warning("Formato de data Java não suportado: %s", type(value))
    return None


def _task_baseline_start_at(task, baseline_number: int):
    """Retorna o LocalDateTime de início da linha de base N (0 = Baseline)."""
    if baseline_number == 0:
        return task.getBaselineStart()
    return task.getBaselineStart(baseline_number)


def _task_baseline_finish_at(task, baseline_number: int):
    """Retorna o LocalDateTime de conclusão da linha de base N (0 = Baseline)."""
    if baseline_number == 0:
        return task.getBaselineFinish()
    return task.getBaselineFinish(baseline_number)


def _call_cost_getter(obj, name: str, baseline_number: int | None = None) -> float:
    """Chama getCost/getBaselineCost/getActualCost no objeto MPXJ, ou 0."""
    getter = getattr(obj, name, None)
    if getter is None:
        return 0.0
    try:
        if baseline_number is None:
            return _numeric_amount(getter())
        if baseline_number == 0:
            try:
                return _numeric_amount(getter())
            except TypeError:
                return _numeric_amount(getter(0))
        return _numeric_amount(getter(baseline_number))
    except Exception:
        return 0.0


def _sum_assignment_costs(
    task, getter_name: str, baseline_number: int | None = None
) -> float:
    """Soma um campo de custo nas atribuições da tarefa."""
    assignments = task.getResourceAssignments()
    if assignments is None:
        return 0.0
    total = 0.0
    for assignment in assignments:
        total += _call_cost_getter(assignment, getter_name, baseline_number)
    return total


def _task_is_summary(task) -> bool:
    """True se a tarefa é resumo (WBS pai)."""
    return bool(_java_bool(task.getSummary()))


def _task_baseline_cost_at(task, baseline_number: int) -> float:
    """Custo próprio da linha de base N: BaselineFixedCost + atribuições."""
    fixed = _call_cost_getter(task, "getBaselineFixedCost", baseline_number)
    return fixed + _sum_assignment_costs(task, "getBaselineCost", baseline_number)


def _task_baseline_accrual_at(task, baseline_number: int):
    """Tipo de acúmulo do custo fixo da linha de base N."""
    getter = getattr(task, "getBaselineFixedCostAccrual", None)
    if getter is None:
        return None
    if baseline_number == 0:
        return getter()
    return getter(baseline_number)


def _java_duration_in_unit(value, time_unit) -> float | None:
    """Converte Duration do MPXJ para a unidade informada."""
    if value is None:
        return None
    try:
        if hasattr(value, "getUnits") and hasattr(value, "getDuration"):
            if value.getUnits() == time_unit:
                return _java_number(value.getDuration())
        if hasattr(value, "getDuration"):
            return _java_number(value.getDuration())
        return _java_number(value)
    except Exception:
        logger.debug("Duração inválida ignorada: %s", value)
        return None


def _task_spi(task) -> float | None:
    """Lê SPI da tarefa quando o arquivo trouxer EVM; senão None."""
    getter = getattr(task, "getSPI", None)
    if getter is None:
        return None
    try:
        return _java_number(getter())
    except Exception:
        return None


def _task_active(task) -> bool | None:
    """Lê flag Active quando disponível."""
    getter = getattr(task, "getActive", None)
    if getter is None:
        return None
    try:
        return _java_bool(getter())
    except Exception:
        return None


def _extract_tasks_from_mpp(project, nome_do_projeto: str) -> tuple[TarefaDTO, ...]:
    """Extrai tarefas de um ProjectFile MPXJ."""
    from org.mpxj import TimeUnit

    tarefas: list[TarefaDTO] = []
    for task in project.getTasks():
        uid = _java_int(task.getUniqueID())
        if uid is None:
            continue

        nome_tarefa = _java_string(task.getName()) or f"Tarefa {uid}"
        wbs = _java_string(task.getWBS()) or _java_string(task.getOutlineNumber())
        tarefas.append(
            TarefaDTO(
                nome_do_projeto=nome_do_projeto,
                id_tarefa=uid,
                nome_tarefa=nome_tarefa,
                data_inicio=_java_date(task.getStart()),
                data_conclusao=_java_date(task.getFinish()),
                desvio_da_conclusao=_java_duration_in_unit(
                    task.getFinishVariance(), TimeUnit.DAYS
                ),
                duracao_da_tarefa=_java_duration_in_unit(
                    task.getDuration(), TimeUnit.DAYS
                ),
                duracao_real_da_tarefa=_java_duration_in_unit(
                    task.getActualDuration(), TimeUnit.DAYS
                ),
                ordem=_java_int(task.getID()),
                spi_da_tarefa=_task_spi(task),
                id_obra=None,
                tarefa_e_resumo=_java_bool(task.getSummary()),
                tarefa_esta_ativa=_task_active(task),
                wbs_da_tarefa=wbs,
            )
        )

    return tuple(tarefas)


def _to_start_of_day(value):
    """Normaliza LocalDateTime/LocalDate Java para meia-noite do dia."""
    if value is None:
        return None
    if hasattr(value, "toLocalDate"):
        return value.toLocalDate().atStartOfDay()
    if hasattr(value, "atStartOfDay"):
        return value.atStartOfDay()
    return value


def _numeric_amount(value) -> float:
    """Extrai valor numérico de Number/Duration (0 se vazio)."""
    if value is None:
        return 0.0
    try:
        if hasattr(value, "getDuration"):
            amount = _java_number(value.getDuration())
            return amount or 0.0
        amount = _java_number(value)
        return amount or 0.0
    except Exception:
        return 0.0


def _create_day_ranges(helper, start, finish):
    """Cria ranges diários half-open [start, finish+1day)."""
    from org.mpxj import TimescaleUnits

    if start is None or finish is None:
        return None
    end_exclusive = finish.toLocalDate().plusDays(1).atStartOfDay()
    if not end_exclusive.isAfter(start):
        end_exclusive = start.toLocalDate().plusDays(1).atStartOfDay()
    ranges = helper.createTimescale(start, end_exclusive, TimescaleUnits.DAYS)
    if ranges is None or ranges.isEmpty():
        return None
    return ranges


def _list_amount_at(values, index: int) -> float:
    """Lê um Number/Duration de uma lista Java no índice, ou 0."""
    if values is None or index >= values.size():
        return 0.0
    return _numeric_amount(values.get(index))


def _accrual_kind(accrual) -> str:
    """Normaliza AccrueType do MPXJ para START, END ou PRORATED."""
    from org.mpxj import AccrueType

    if accrual is None:
        return "PRORATED"
    if accrual == AccrueType.START:
        return "START"
    if accrual == AccrueType.END:
        return "END"
    return "PRORATED"


def _is_working_day(calendar, java_datetime) -> bool:
    """Indica se a data cai em dia útil no calendário da tarefa."""
    if calendar is None or java_datetime is None:
        return True
    local_date = (
        java_datetime.toLocalDate()
        if hasattr(java_datetime, "toLocalDate")
        else java_datetime
    )
    try:
        return bool(calendar.isWorkingDate(local_date))
    except Exception:
        logger.debug("Falha ao consultar calendário em %s", java_datetime)
        return True


def _working_indices(calendar, ranges) -> list[int]:
    """Índices de ranges diários que caem em dia útil."""
    return [
        index
        for index in range(ranges.size())
        if _is_working_day(calendar, ranges.get(index).getStart())
    ]


def _spread_amount(
    amount: float, working_indices: list[int], accrual, size: int
) -> list[float]:
    """Distribui um total pelos dias úteis conforme o acúmulo do Project."""
    result = [0.0] * size
    if amount <= _COST_EPS or not working_indices:
        return result

    kind = _accrual_kind(accrual)
    if kind == "START":
        result[working_indices[0]] = amount
        return result
    if kind == "END":
        result[working_indices[-1]] = amount
        return result

    day_count = len(working_indices)
    share = amount / day_count
    allocated = 0.0
    for position, index in enumerate(working_indices):
        if position == day_count - 1:
            result[index] = amount - allocated
        else:
            result[index] = share
            allocated += share
    return result


def _task_scalar_cost(task) -> float:
    """Custo planejado próprio: FixedCost + soma das atribuições (sem rollup)."""
    fixed = _call_cost_getter(task, "getFixedCost")
    return fixed + _sum_assignment_costs(task, "getCost")


def _task_scalar_actual_cost(task) -> float:
    """Custo real próprio: atribuições; na folha, ActualCost da tarefa se for maior."""
    assignment_actual = _sum_assignment_costs(task, "getActualCost")
    if _task_is_summary(task):
        return assignment_actual
    task_actual = _call_cost_getter(task, "getActualCost")
    return max(assignment_actual, task_actual)


def _day_in_interval(day: date | None, start, finish) -> bool:
    """True se o dia está entre start e finish (inclusive)."""
    if day is None:
        return False
    start_day = _java_date(start)
    finish_day = _java_date(finish)
    if start_day is not None and day < start_day:
        return False
    if finish_day is not None and day > finish_day:
        return False
    return True


def _timephased_or_spread(
    native_values,
    ranges,
    scalar: float,
    calendar,
    accrual,
    working_indices: list[int] | None = None,
) -> tuple[list[float], bool, bool]:
    """Usa o nativo se bater com o total próprio; senão rateia. Pai sem custo próprio zera."""
    size = ranges.size()
    if scalar <= _COST_EPS:
        return [0.0] * size, False, False

    native = [_list_amount_at(native_values, index) for index in range(size)]
    native_sum = sum(native)
    inflate_limit = scalar * _NATIVE_INFLATE_RATIO + _NATIVE_INFLATE_ABS
    if _COST_EPS < native_sum <= inflate_limit:
        return native, False, False

    indices = working_indices if working_indices is not None else _working_indices(
        calendar, ranges
    )
    spread = _spread_amount(scalar, indices, accrual, size)
    inflated = native_sum > inflate_limit
    return spread, True, inflated


def _extract_conjunto_dados_faseados(
    project, nome_do_projeto: str
) -> tuple[ConjuntoDadosFaseadosTarefaDTO, ...]:
    """Extrai ConjuntoDeDadosFaseadosNoTempoDaTarefa (custo e custo real)."""
    from org.mpxj.common import TimescaleHelper

    helper = TimescaleHelper()
    rows: list[ConjuntoDadosFaseadosTarefaDTO] = []
    seen: set[tuple[int, date]] = set()
    tasks_with_scalar = 0
    fallback_tasks = 0
    inflated_slices = 0

    for task in project.getTasks():
        uid = _java_int(task.getUniqueID())
        if uid is None:
            continue

        start = _to_start_of_day(task.getStart())
        finish = _to_start_of_day(task.getFinish())
        ranges = _create_day_ranges(helper, start, finish)
        if ranges is None:
            continue

        scalar_cost = _task_scalar_cost(task)
        scalar_actual = _task_scalar_actual_cost(task)
        if scalar_cost > _COST_EPS or scalar_actual > _COST_EPS:
            tasks_with_scalar += 1

        calendar = task.getEffectiveCalendar()
        accrual = (
            task.getFixedCostAccrual() if hasattr(task, "getFixedCostAccrual") else None
        )
        working_indices = _working_indices(calendar, ranges)

        native_cost = task.getTimephasedCost(ranges)
        native_actual = task.getTimephasedActualCost(ranges)
        native_budget = None
        budget_getter = getattr(task, "getTimephasedBudgetCost", None)
        if budget_getter is not None:
            native_budget = budget_getter(ranges)

        costs, used_cost_fallback, cost_inflated = _timephased_or_spread(
            native_cost, ranges, scalar_cost, calendar, accrual, working_indices
        )
        if native_budget is not None:
            for index in range(ranges.size()):
                costs[index] += _list_amount_at(native_budget, index)

        actual_start = task.getActualStart() or start
        actual_finish = task.getActualFinish() or finish
        actual_indices = [
            index
            for index in working_indices
            if _day_in_interval(
                _java_date(ranges.get(index).getStart()), actual_start, actual_finish
            )
        ]
        actuals, used_actual_fallback, actual_inflated = _timephased_or_spread(
            native_actual,
            ranges,
            scalar_actual,
            calendar,
            accrual,
            actual_indices,
        )
        if used_cost_fallback or used_actual_fallback:
            fallback_tasks += 1
        inflated_slices += int(cost_inflated) + int(actual_inflated)

        for index in range(ranges.size()):
            custo = costs[index]
            custo_real = actuals[index]
            if custo <= _COST_EPS and custo_real <= _COST_EPS:
                continue

            day = _java_date(ranges.get(index).getStart())
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
        "Faseados '%s': %d linha(s); %d tarefa(s) com custo próprio; "
        "%d com rateio por dia útil; %d fatia(s) com timephased inflado.",
        nome_do_projeto,
        len(rows),
        tasks_with_scalar,
        fallback_tasks,
        inflated_slices,
    )
    return tuple(rows)


def _extract_linhas_base_faseadas(
    project, nome_do_projeto: str
) -> tuple[LinhaBaseFaseadaTarefaDTO, ...]:
    """Extrai LinhaDeBaseDoConjuntoDeDadosFaseadosNoTempoDaTarefa via MPXJ."""
    from org.mpxj.common import TimescaleHelper

    helper = TimescaleHelper()
    rows: list[LinhaBaseFaseadaTarefaDTO] = []
    seen: set[tuple[int, date, int]] = set()
    tasks_with_scalar = 0
    fallback_tasks = 0
    inflated_slices = 0

    for task in project.getTasks():
        uid = _java_int(task.getUniqueID())
        if uid is None:
            continue

        calendar = task.getEffectiveCalendar()
        used_fallback_for_task = False

        for baseline_number in _BASELINE_INDEXES:
            start = _to_start_of_day(_task_baseline_start_at(task, baseline_number))
            finish = _to_start_of_day(_task_baseline_finish_at(task, baseline_number))
            ranges = _create_day_ranges(helper, start, finish)
            if ranges is None:
                continue

            scalar = _task_baseline_cost_at(task, baseline_number)
            if scalar > _COST_EPS:
                tasks_with_scalar += 1

            native_cost = task.getTimephasedBaselineCost(baseline_number, ranges)
            costs, used_fallback, inflated = _timephased_or_spread(
                native_cost,
                ranges,
                scalar,
                calendar,
                _task_baseline_accrual_at(task, baseline_number),
            )
            if used_fallback:
                used_fallback_for_task = True
            if inflated:
                inflated_slices += 1

            for index in range(ranges.size()):
                cost_amount = costs[index]
                if cost_amount <= _COST_EPS:
                    continue

                day = _java_date(ranges.get(index).getStart())
                if day is None:
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
        "Linhas de base faseadas '%s': %d linha(s); %d baseline(s) com custo próprio; "
        "%d tarefa(s) com rateio por dia útil; %d fatia(s) com timephased inflado.",
        nome_do_projeto,
        len(rows),
        tasks_with_scalar,
        fallback_tasks,
        inflated_slices,
    )
    return tuple(rows)


def parse_ms_project_mpp(mpp_path: Path) -> ArquivoProjetoDTO:
    """Parseia um arquivo .mpp nativo do MS Project via MPXJ."""
    _ensure_jvm()

    from org.mpxj.reader import UniversalProjectReader

    project = UniversalProjectReader().read(str(mpp_path))
    properties = project.getProjectProperties()

    nome_do_projeto = (
        _java_string(properties.getProjectTitle())
        or _java_string(properties.getName())
        or mpp_path.stem
    )

    return ArquivoProjetoDTO(
        nome_do_projeto=nome_do_projeto,
        tarefas=_extract_tasks_from_mpp(project, nome_do_projeto),
        conjunto_dados_faseados=_extract_conjunto_dados_faseados(
            project, nome_do_projeto
        ),
        linhas_base_faseadas=_extract_linhas_base_faseadas(project, nome_do_projeto),
    )
