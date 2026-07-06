"""Leitura de arquivos MS Project (.mpp) para DTOs do pipeline."""

from __future__ import annotations

import logging
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
class ProjetoDTO:
    """DTO imutável para dados de projeto extraídos do MS Project."""

    nome_projeto: str
    gerente: str | None
    data_inicio: date | None
    data_fim: date | None
    percentual_concluido: float | None
    tarefas: tuple[TarefaDTO, ...]


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
            jpype.startJVM()
        except jpype.JVMNotFoundException as exc:
            raise RuntimeError(
                "Leitura de .mpp requer Java (JRE 8+). "
                "A imagem Docker do projeto já instala esse requisito."
            ) from exc

    _jvm_started = True


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


def _task_baseline_start(task) -> date | None:
    """Lê início da linha de base (plano base) da tarefa."""
    baseline_start = _java_date(task.getBaselineStart())
    if baseline_start is not None:
        return baseline_start
    return _java_date(task.getBaselineStart(1))


def _task_baseline_finish(task) -> date | None:
    """Lê conclusão da linha de base (plano base) da tarefa."""
    baseline_finish = _java_date(task.getBaselineFinish())
    if baseline_finish is not None:
        return baseline_finish
    return _java_date(task.getBaselineFinish(1))


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
    )
