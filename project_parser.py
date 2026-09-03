"""Leitura de arquivos MS Project (.mpp) para DTOs do pipeline."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_FILE_EXTENSION = ".mpp"


@dataclass(frozen=True, slots=True)
class TarefaDTO:
    """DTO imutável para dados de tarefa extraídos do MS Project."""

    id_tarefa_project: int
    nome_tarefa: str
    data_inicio: date | None
    data_fim: date | None
    inicio_do_plano_base: date | None
    conclusao_do_plano_base: date | None
    percentual_concluido: float | None
    duracao: float | None
    custo: float | None
    trabalho: float | None
    outline_level: int | None
    outline_number: str | None


@dataclass(frozen=True, slots=True)
class LinhaBaseFaseadaTarefaDTO:
    """Linha de baseline faseada no tempo (equivalente ao dataset do Project Online)."""

    id_tarefa_project: int
    hora_por_dia: date
    numero_linha_base: int


@dataclass(frozen=True, slots=True)
class ProjetoDTO:
    """DTO imutável para dados de projeto extraídos do MS Project."""

    nome_projeto: str
    gerente: str | None
    data_inicio: date | None
    data_fim: date | None
    percentual_concluido: float | None
    tarefas: tuple[TarefaDTO, ...]
    linhas_base_faseadas: tuple[LinhaBaseFaseadaTarefaDTO, ...] = ()


def is_project_file(path: Path) -> bool:
    """Indica se o arquivo tem extensão suportada (.mpp)."""
    return path.suffix.lower() == PROJECT_FILE_EXTENSION


def parse_project_file(path: Path) -> ProjetoDTO:
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


def _task_baseline_start(task) -> date | None:
    """Lê início da linha de base (plano base) da tarefa."""
    baseline_start = _java_date(_task_baseline_start_at(task, 0))
    if baseline_start is not None:
        return baseline_start
    return _java_date(_task_baseline_start_at(task, 1))


def _task_baseline_finish(task) -> date | None:
    """Lê conclusão da linha de base (plano base) da tarefa."""
    baseline_finish = _java_date(_task_baseline_finish_at(task, 0))
    if baseline_finish is not None:
        return baseline_finish
    return _java_date(_task_baseline_finish_at(task, 1))


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


def _extract_tasks_from_mpp(project) -> tuple[TarefaDTO, ...]:
    """Extrai tarefas de um ProjectFile MPXJ."""
    from org.mpxj import TimeUnit

    tarefas: list[TarefaDTO] = []
    for task in project.getTasks():
        uid = _java_int(task.getUniqueID())
        if uid is None:
            continue

        nome_tarefa = _java_string(task.getName()) or f"Tarefa {uid}"
        tarefas.append(
            TarefaDTO(
                id_tarefa_project=uid,
                nome_tarefa=nome_tarefa,
                data_inicio=_java_date(task.getStart()),
                data_fim=_java_date(task.getFinish()),
                inicio_do_plano_base=_task_baseline_start(task),
                conclusao_do_plano_base=_task_baseline_finish(task),
                percentual_concluido=_java_number(task.getPercentageComplete()),
                duracao=_java_duration_in_unit(task.getDuration(), TimeUnit.DAYS),
                custo=_java_number(task.getCost()),
                trabalho=_java_duration_in_unit(task.getWork(), TimeUnit.HOURS),
                outline_level=_java_int(task.getOutlineLevel()),
                outline_number=_java_string(task.getOutlineNumber()),
            )
        )

    return tuple(tarefas)


# Índices de baseline do MS Project: 0 = Baseline, 1..10 = Baseline1..Baseline10.
_BASELINE_INDEXES = range(0, 11)


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


def _extract_linhas_base_faseadas(project) -> tuple[LinhaBaseFaseadaTarefaDTO, ...]:
    """Extrai LinhaDeBaseDoConjuntoDeDadosFaseadosNoTempoDaTarefa via MPXJ."""
    from org.mpxj import TimeUnit, TimescaleUnits
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
            if start is None or finish is None:
                continue

            # Timescale half-open: fim exclusivo = dia seguinte ao finish.
            end_exclusive = finish.toLocalDate().plusDays(1).atStartOfDay()
            if not end_exclusive.isAfter(start):
                end_exclusive = start.toLocalDate().plusDays(1).atStartOfDay()

            ranges = helper.createTimescale(start, end_exclusive, TimescaleUnits.DAYS)
            if ranges is None or ranges.isEmpty():
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
                    cost_amount = _java_number(cost_list.get(index)) or 0.0
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
                        id_tarefa_project=uid,
                        hora_por_dia=day,
                        numero_linha_base=baseline_number,
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
                            id_tarefa_project=uid,
                            hora_por_dia=day,
                            numero_linha_base=baseline_number,
                        )
                    )

    return tuple(rows)


def parse_ms_project_mpp(mpp_path: Path) -> ProjetoDTO:
    """Parseia um arquivo .mpp nativo do MS Project via MPXJ."""
    _ensure_jvm()

    from org.mpxj.reader import UniversalProjectReader

    project = UniversalProjectReader().read(str(mpp_path))
    properties = project.getProjectProperties()

    nome_projeto = (
        _java_string(properties.getProjectTitle())
        or _java_string(properties.getName())
        or mpp_path.stem
    )
    percentual = _java_number(properties.getPercentageComplete())

    return ProjetoDTO(
        nome_projeto=nome_projeto,
        gerente=_java_string(properties.getManager()),
        data_inicio=_java_date(properties.getStartDate()),
        data_fim=_java_date(properties.getFinishDate()),
        percentual_concluido=percentual,
        tarefas=_extract_tasks_from_mpp(project),
        linhas_base_faseadas=_extract_linhas_base_faseadas(project),
    )
