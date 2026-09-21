"""JVM, conversões Java e getters MPXJ apontados pelo field_catalog."""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

from cost_engine import combine_resource_and_fixed, own_or_assignment

logger = logging.getLogger(__name__)

_jvm_started = False


def ensure_jvm() -> None:
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


def java_number(value) -> float | None:
    """Converte tipos numéricos Java em float Python."""
    if value is None:
        return None
    if hasattr(value, "doubleValue"):
        return float(value.doubleValue())
    return float(value)


def java_string(value) -> str | None:
    """Converte strings Java em str Python."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def java_int(value) -> int | None:
    """Converte tipos inteiros Java em int Python."""
    if value is None:
        return None
    if hasattr(value, "intValue"):
        return int(value.intValue())
    return int(value)


def java_bool(value) -> bool | None:
    """Converte Boolean Java em bool Python."""
    if value is None:
        return None
    if hasattr(value, "booleanValue"):
        return bool(value.booleanValue())
    return bool(value)


def java_date(value) -> date | None:
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


def java_duration_in_unit(value, time_unit) -> float | None:
    """Converte Duration do MPXJ para a unidade informada."""
    if value is None:
        return None
    try:
        if hasattr(value, "getUnits") and hasattr(value, "getDuration"):
            if value.getUnits() == time_unit:
                return java_number(value.getDuration())
        if hasattr(value, "getDuration"):
            return java_number(value.getDuration())
        return java_number(value)
    except Exception:
        logger.debug("Duração inválida ignorada: %s", value)
        return None


def numeric_amount(value) -> float:
    """Extrai valor numérico de Number/Duration (0 se vazio)."""
    if value is None:
        return 0.0
    try:
        if hasattr(value, "getDuration"):
            amount = java_number(value.getDuration())
            return amount or 0.0
        amount = java_number(value)
        return amount or 0.0
    except Exception:
        return 0.0


def to_start_of_day(value):
    """Normaliza LocalDateTime/LocalDate Java para meia-noite do dia."""
    if value is None:
        return None
    if hasattr(value, "toLocalDate"):
        return value.toLocalDate().atStartOfDay()
    if hasattr(value, "atStartOfDay"):
        return value.atStartOfDay()
    return value


def call_cost_getter(obj, name: str, baseline_number: int | None = None) -> float:
    """Chama getCost/getBaselineCost/getActualCost no objeto MPXJ, ou 0."""
    getter = getattr(obj, name, None)
    if getter is None:
        return 0.0
    try:
        if baseline_number is None:
            return numeric_amount(getter())
        if baseline_number == 0:
            try:
                return numeric_amount(getter())
            except TypeError:
                return numeric_amount(getter(0))
        return numeric_amount(getter(baseline_number))
    except Exception:
        return 0.0


def sum_assignment_costs(
    task, getter_name: str, baseline_number: int | None = None
) -> float:
    """Soma um campo de custo nas atribuições da tarefa."""
    assignments = task.getResourceAssignments()
    if assignments is None:
        return 0.0
    total = 0.0
    for assignment in assignments:
        total += call_cost_getter(assignment, getter_name, baseline_number)
    return total


def task_scalar_cost(task) -> float:
    """Custo próprio planejado: FixedCost + soma das atribuições (sem rollup)."""
    fixed = call_cost_getter(task, "getFixedCost")
    return fixed + sum_assignment_costs(task, "getCost")


def task_scalar_actual_cost(task) -> float:
    """Custo real próprio (atribuições + custo fixo apropriado; sem rollup)."""
    assignment_actual = sum_assignment_costs(task, "getActualCost")
    own_cap = task_scalar_cost(task)
    task_actual = call_cost_getter(task, "getActualCost")
    return own_or_assignment(task_actual, assignment_actual, own_cap)


def task_scalar_remaining_cost(task) -> float:
    """Remaining próprio: max(atribuições, total próprio − real próprio)."""
    assignment_remaining = sum_assignment_costs(task, "getRemainingCost")
    implied = max(0.0, task_scalar_cost(task) - task_scalar_actual_cost(task))
    return max(assignment_remaining, implied)


def task_scalar_baseline_cost(task, baseline_number: int) -> float:
    """Custo próprio da linha de base N: BaselineFixedCost + atribuições."""
    fixed = call_cost_getter(task, "getBaselineFixedCost", baseline_number)
    return fixed + sum_assignment_costs(task, "getBaselineCost", baseline_number)


def task_baseline_start_at(task, baseline_number: int):
    """Retorna o LocalDateTime de início da linha de base N (0 = Baseline)."""
    if baseline_number == 0:
        return task.getBaselineStart()
    return task.getBaselineStart(baseline_number)


def task_baseline_finish_at(task, baseline_number: int):
    """Retorna o LocalDateTime de conclusão da linha de base N (0 = Baseline)."""
    if baseline_number == 0:
        return task.getBaselineFinish()
    return task.getBaselineFinish(baseline_number)


def task_baseline_accrual_at(task, baseline_number: int):
    """Tipo de acúmulo do custo fixo da linha de base N."""
    getter = getattr(task, "getBaselineFixedCostAccrual", None)
    if getter is None:
        return None
    if baseline_number == 0:
        return getter()
    return getter(baseline_number)


def task_spi(task) -> float | None:
    """Lê SPI da tarefa quando o arquivo trouxer EVM; senão None."""
    getter = getattr(task, "getSPI", None)
    if getter is None:
        return None
    try:
        return java_number(getter())
    except Exception:
        return None


def task_active(task) -> bool | None:
    """Lê flag Active quando disponível."""
    getter = getattr(task, "getActive", None)
    if getter is None:
        return None
    try:
        return java_bool(getter())
    except Exception:
        return None


def mpxj_accrual_kind(accrual) -> str:
    """Normaliza AccrueType do MPXJ para START, END ou PRORATED."""
    from org.mpxj import AccrueType

    if accrual is None:
        return "PRORATED"
    if accrual == AccrueType.START:
        return "START"
    if accrual == AccrueType.END:
        return "END"
    return "PRORATED"


def task_accrual_kind(task) -> str:
    """Acúmulo do custo fixo corrente da tarefa."""
    accrual = (
        task.getFixedCostAccrual() if hasattr(task, "getFixedCostAccrual") else None
    )
    return mpxj_accrual_kind(accrual)


def create_day_ranges(helper, start, finish):
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


def list_amount_at(values, index: int) -> float:
    """Lê um Number/Duration de uma lista Java no índice, ou 0."""
    if values is None or index >= values.size():
        return 0.0
    return numeric_amount(values.get(index))


def java_list_amounts(values, size: int) -> list[float]:
    """Converte uma lista Java de Number/Duration em list[float]."""
    return [list_amount_at(values, index) for index in range(size)]


def _call_timephased(task, name: str, ranges):
    getter = getattr(task, name, None)
    if getter is None:
        return None
    try:
        return getter(ranges)
    except Exception:
        logger.debug("Falha em %s", name)
        return None


def native_actual_cost(task, ranges) -> list[float]:
    """Timephased actual (recurso + fixo, sem duplicar)."""
    size = ranges.size()
    resource = java_list_amounts(task.getTimephasedActualCost(ranges), size)
    fixed = java_list_amounts(
        _call_timephased(task, "getTimephasedActualFixedCost", ranges), size
    )
    return combine_resource_and_fixed(resource, fixed)


def native_remaining_cost(task, ranges) -> list[float]:
    """Timephased remaining (recurso + fixo, sem duplicar)."""
    size = ranges.size()
    resource = java_list_amounts(task.getTimephasedRemainingCost(ranges), size)
    fixed = java_list_amounts(
        _call_timephased(task, "getTimephasedRemainingFixedCost", ranges), size
    )
    return combine_resource_and_fixed(resource, fixed)


def native_baseline_cost(task, baseline_number: int, ranges) -> list[float]:
    """Timephased da linha de base N."""
    return java_list_amounts(
        task.getTimephasedBaselineCost(baseline_number, ranges), ranges.size()
    )


def is_working_day(calendar, java_datetime) -> bool:
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


def working_indices(calendar, ranges) -> list[int]:
    """Índices de ranges diários que caem em dia útil."""
    return [
        index
        for index in range(ranges.size())
        if is_working_day(calendar, ranges.get(index).getStart())
    ]


def days_from_ranges(ranges) -> list[date | None]:
    """Datas Python dos starts de cada range diário."""
    return [java_date(ranges.get(index).getStart()) for index in range(ranges.size())]


def day_in_interval(day: date | None, start, finish) -> bool:
    """True se o dia está entre start e finish (inclusive)."""
    if day is None:
        return False
    start_day = java_date(start)
    finish_day = java_date(finish)
    if start_day is not None and day < start_day:
        return False
    if finish_day is not None and day > finish_day:
        return False
    return True


def project_status_date(project) -> date:
    """Status Date do .mpp; senão Current Date; senão hoje."""
    properties = project.getProjectProperties()
    for getter_name in ("getStatusDate", "getCurrentDate"):
        getter = getattr(properties, getter_name, None)
        if getter is None:
            continue
        try:
            resolved = java_date(getter())
        except Exception:
            resolved = None
        if resolved is not None:
            return resolved
    return date.today()


def project_nome(project, mpp_path: Path) -> str:
    """Título do projeto, nome, ou stem do arquivo."""
    properties = project.getProjectProperties()
    return (
        java_string(properties.getProjectTitle())
        or java_string(properties.getName())
        or mpp_path.stem
    )
