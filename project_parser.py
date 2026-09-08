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


def _duration_amount(value) -> float:
    """Extrai o valor numérico de um Duration MPXJ (0 se vazio)."""
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


def _extract_conjunto_dados_faseados(
    project, nome_do_projeto: str
) -> tuple[ConjuntoDadosFaseadosTarefaDTO, ...]:
    """Extrai ConjuntoDeDadosFaseadosNoTempoDaTarefa (custo e custo real)."""
    from org.mpxj.common import TimescaleHelper

    helper = TimescaleHelper()
    rows: list[ConjuntoDadosFaseadosTarefaDTO] = []
    seen: set[tuple[int, date]] = set()

    for task in project.getTasks():
        uid = _java_int(task.getUniqueID())
        if uid is None:
            continue

        start = _to_start_of_day(task.getStart())
        finish = _to_start_of_day(task.getFinish())
        ranges = _create_day_ranges(helper, start, finish)
        if ranges is None:
            continue

        cost_list = task.getTimephasedCost(ranges)
        actual_cost_list = task.getTimephasedActualCost(ranges)

        for index in range(ranges.size()):
            custo = (
                _numeric_amount(cost_list.get(index))
                if cost_list is not None and index < cost_list.size()
                else 0.0
            )
            custo_real = (
                _numeric_amount(actual_cost_list.get(index))
                if actual_cost_list is not None and index < actual_cost_list.size()
                else 0.0
            )
            if custo <= 0 and custo_real <= 0:
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

    return tuple(rows)


def _extract_linhas_base_faseadas(
    project, nome_do_projeto: str
) -> tuple[LinhaBaseFaseadaTarefaDTO, ...]:
    """Extrai LinhaDeBaseDoConjuntoDeDadosFaseadosNoTempoDaTarefa via MPXJ."""
    from org.mpxj import TimeUnit
    from org.mpxj.common import TimescaleHelper

    helper = TimescaleHelper()
    rows: list[LinhaBaseFaseadaTarefaDTO] = []
    seen: set[tuple[int, date, int]] = set()

    for task in project.getTasks():
        uid = _java_int(task.getUniqueID())
        if uid is None:
            continue

        for baseline_number in _BASELINE_INDEXES:
            start = _to_start_of_day(_task_baseline_start_at(task, baseline_number))
            finish = _to_start_of_day(_task_baseline_finish_at(task, baseline_number))
            ranges = _create_day_ranges(helper, start, finish)
            if ranges is None:
                continue

            work_list = task.getTimephasedBaselineWork(
                baseline_number, ranges, TimeUnit.HOURS
            )
            cost_list = task.getTimephasedBaselineCost(baseline_number, ranges)

            emitted_for_baseline = False
            for index in range(ranges.size()):
                work_amount = (
                    _duration_amount(work_list.get(index))
                    if work_list is not None and index < work_list.size()
                    else 0.0
                )
                cost_amount = 0.0
                if cost_list is not None and index < cost_list.size():
                    cost_amount = _numeric_amount(cost_list.get(index))
                if work_amount <= 0 and cost_amount <= 0:
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
                emitted_for_baseline = True

            # Sem timephased numérico: gera um ponto por dia no intervalo da baseline.
            if not emitted_for_baseline:
                for index in range(ranges.size()):
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
                            custo_de_linha_base=0.0,
                        )
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
