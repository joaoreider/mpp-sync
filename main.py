"""Pipeline ETL: pasta local -> MS Project (.mpp) -> banco relacional."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from config import Settings, load_settings
from models import Projeto, Tarefa, get_session_factory, init_db
from project_parser import (
    PROJECT_FILE_EXTENSION,
    ProjetoDTO,
    TarefaDTO,
    is_project_file,
    parse_project_file,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

WATCH_DEBOUNCE_SECONDS = 5.0
FILE_STABILITY_CHECK_INTERVAL_SECONDS = 1.0
FILE_STABILITY_REQUIRED_MATCHES = 2
FILE_STABILITY_TIMEOUT_SECONDS = 60.0


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _is_temporary_project_path(path: Path) -> bool:
    """Ignora arquivos temporários comuns durante salvamento no Windows/MS Project."""
    return path.name.startswith(("~$", ".")) or path.suffix.lower() != PROJECT_FILE_EXTENSION


def _is_project_candidate(path: Path) -> bool:
    return is_project_file(path) and not _is_temporary_project_path(path)


def collect_project_files(settings: Settings) -> list[Path]:
    """Lista arquivos .mpp da pasta configurada."""
    project_files = sorted(
        path for path in settings.local_mpp_dir.glob("*.mpp") if path.is_file()
    )
    for project_path in project_files:
        logger.info("Arquivo encontrado: %s", project_path)
    return project_files


def _apply_projeto_fields(projeto: Projeto, dto: ProjetoDTO) -> None:
    """Atualiza campos mutáveis de um projeto existente."""
    projeto.gerente = dto.gerente
    projeto.data_inicio = dto.data_inicio
    projeto.data_fim = dto.data_fim
    projeto.percentual_concluido = dto.percentual_concluido
    projeto.atualizado_em = datetime.now(timezone.utc)


def upsert_projeto(session: Session, dto: ProjetoDTO) -> Projeto:
    """Insere ou atualiza projeto usando nome_projeto como chave natural."""
    projeto = (
        session.query(Projeto)
        .filter(Projeto.nome_projeto == dto.nome_projeto)
        .one_or_none()
    )

    if projeto is None:
        projeto = Projeto(
            nome_projeto=dto.nome_projeto,
            gerente=dto.gerente,
            data_inicio=dto.data_inicio,
            data_fim=dto.data_fim,
            percentual_concluido=dto.percentual_concluido,
            atualizado_em=datetime.now(timezone.utc),
        )
        session.add(projeto)
        session.flush()
        return projeto

    _apply_projeto_fields(projeto, dto)
    session.flush()
    return projeto


def _apply_tarefa_fields(tarefa: Tarefa, dto: TarefaDTO) -> None:
    """Atualiza campos mutáveis de uma tarefa existente."""
    tarefa.nome_tarefa = dto.nome_tarefa
    tarefa.data_inicio = dto.data_inicio
    tarefa.data_fim = dto.data_fim
    tarefa.inicio_do_plano_base = dto.inicio_do_plano_base
    tarefa.conclusao_do_plano_base = dto.conclusao_do_plano_base
    tarefa.percentual_concluido = dto.percentual_concluido
    tarefa.duracao = dto.duracao
    tarefa.custo = dto.custo
    tarefa.trabalho = dto.trabalho


def persist_projeto(session: Session, dto: ProjetoDTO) -> Projeto:
    """Persiste projeto e todas as tarefas associadas."""
    projeto = upsert_projeto(session, dto)
    existing_by_uid = {
        tarefa.id_tarefa_project: tarefa
        for tarefa in session.query(Tarefa)
        .filter(Tarefa.id_projeto == projeto.id)
        .all()
    }

    for tarefa_dto in dto.tarefas:
        tarefa = existing_by_uid.get(tarefa_dto.id_tarefa_project)
        if tarefa is None:
            session.add(
                Tarefa(
                    id_projeto=projeto.id,
                    nome_tarefa=tarefa_dto.nome_tarefa,
                    data_inicio=tarefa_dto.data_inicio,
                    data_fim=tarefa_dto.data_fim,
                    inicio_do_plano_base=tarefa_dto.inicio_do_plano_base,
                    conclusao_do_plano_base=tarefa_dto.conclusao_do_plano_base,
                    percentual_concluido=tarefa_dto.percentual_concluido,
                    duracao=tarefa_dto.duracao,
                    custo=tarefa_dto.custo,
                    trabalho=tarefa_dto.trabalho,
                    id_tarefa_project=tarefa_dto.id_tarefa_project,
                )
            )
        else:
            _apply_tarefa_fields(tarefa, tarefa_dto)

    return projeto


def process_project_file(session: Session, project_path: Path) -> None:
    """Processa um único arquivo .mpp com commit transacional."""
    parse_start = time.perf_counter()
    dto = parse_project_file(project_path)
    logger.info(
        "Leitura de '%s' concluída em %d ms (%d tarefa(s)).",
        project_path.name,
        _elapsed_ms(parse_start),
        len(dto.tarefas),
    )

    persist_start = time.perf_counter()
    persist_projeto(session, dto)
    session.commit()
    logger.info(
        "Projeto '%s' persistido em %d ms.",
        dto.nome_projeto,
        _elapsed_ms(persist_start),
    )


class PipelineRuntime:
    """Mantém recursos compartilhados para processar eventos do watcher."""

    def __init__(self, settings: Settings) -> None:
        db_start = time.perf_counter()
        init_db(settings.database_url)
        self.session_factory = get_session_factory(settings.database_url)
        self._process_lock = threading.Lock()
        logger.info("Banco inicializado em %d ms.", _elapsed_ms(db_start))

    def process_path(self, project_path: Path) -> None:
        """Processa um arquivo por vez para evitar disputa entre eventos próximos."""
        with self._process_lock:
            with self.session_factory() as session:
                process_project_file(session, project_path)


def wait_until_file_is_stable(project_path: Path) -> bool:
    """Aguarda tamanho e mtime estabilizarem antes de ler o .mpp."""
    deadline = time.monotonic() + FILE_STABILITY_TIMEOUT_SECONDS
    previous_signature: tuple[int, int] | None = None
    stable_matches = 0

    while time.monotonic() < deadline:
        try:
            stat = project_path.stat()
        except FileNotFoundError:
            stable_matches = 0
            previous_signature = None
            time.sleep(FILE_STABILITY_CHECK_INTERVAL_SECONDS)
            continue

        signature = (stat.st_size, stat.st_mtime_ns)
        if stat.st_size > 0 and signature == previous_signature:
            stable_matches += 1
            if stable_matches >= FILE_STABILITY_REQUIRED_MATCHES:
                logger.info("Arquivo estável para processamento: %s", project_path)
                return True
        else:
            stable_matches = 0
            previous_signature = signature

        time.sleep(FILE_STABILITY_CHECK_INTERVAL_SECONDS)

    logger.warning(
        "Tempo esgotado aguardando estabilidade do arquivo: %s",
        project_path,
    )
    return False


class MppWatchHandler(FileSystemEventHandler):
    """Agenda processamento de arquivos .mpp detectados pelo watchdog."""

    def __init__(self, runtime: PipelineRuntime) -> None:
        super().__init__()
        self._runtime = runtime
        self._timers: dict[Path, threading.Timer] = {}
        self._timer_lock = threading.Lock()

    def on_created(self, event: FileSystemEvent) -> None:
        self._schedule_event_path(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._schedule_event_path(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        dest_path = getattr(event, "dest_path", "")
        if dest_path:
            self._schedule_path(Path(dest_path))

    def _schedule_event_path(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._schedule_path(Path(event.src_path))

    def _schedule_path(self, project_path: Path) -> None:
        if not _is_project_candidate(project_path):
            return

        with self._timer_lock:
            existing_timer = self._timers.pop(project_path, None)
            if existing_timer is not None:
                existing_timer.cancel()

            timer = threading.Timer(
                WATCH_DEBOUNCE_SECONDS,
                self._process_after_debounce,
                args=(project_path,),
            )
            timer.daemon = True
            self._timers[project_path] = timer
            timer.start()

        logger.info(
            "Arquivo .mpp detectado; aguardando %.1f s antes de validar: %s",
            WATCH_DEBOUNCE_SECONDS,
            project_path,
        )

    def _process_after_debounce(self, project_path: Path) -> None:
        with self._timer_lock:
            self._timers.pop(project_path, None)

        if not project_path.exists():
            logger.warning("Arquivo detectado não existe mais: %s", project_path)
            return

        if not wait_until_file_is_stable(project_path):
            return

        try:
            self._runtime.process_path(project_path)
        except Exception:
            logger.exception("Falha ao processar arquivo detectado: %s", project_path)


def run_pipeline(settings: Settings) -> None:
    """Executa o pipeline completo de ETL."""
    pipeline_start = time.perf_counter()

    runtime = PipelineRuntime(settings)

    logger.info("Pasta observada: %s", settings.local_mpp_dir)
    project_files = collect_project_files(settings)

    if not project_files:
        logger.warning(
            "Nenhum arquivo %s encontrado em %s.",
            PROJECT_FILE_EXTENSION,
            settings.local_mpp_dir,
        )
        return

    success_count = 0
    failure_count = 0

    for project_path in project_files:
        try:
            runtime.process_path(project_path)
            success_count += 1
        except Exception:
            failure_count += 1
            logger.exception("Falha ao processar arquivo: %s", project_path)

    logger.info(
        "Pipeline finalizado em %d ms. Sucesso: %d | Falhas: %d | Total: %d",
        _elapsed_ms(pipeline_start),
        success_count,
        failure_count,
        len(project_files),
    )


def watch_project_folder(settings: Settings) -> None:
    """Observa continuamente a pasta local e processa .mpp salvos."""
    service = WatcherService(settings)
    service.start()

    try:
        while service.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Interrupção recebida. Encerrando watcher...")
    finally:
        service.stop()


class WatcherService:
    """Controla o watcher em background para uso por CLI ou interface gráfica."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._observer: Observer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()

    def start(self) -> None:
        """Inicia a observação da pasta configurada em uma thread daemon."""
        with self._lock:
            if self.is_running:
                return

            runtime = PipelineRuntime(self._settings)
            event_handler = MppWatchHandler(runtime)
            observer = Observer()
            observer.schedule(
                event_handler,
                str(self._settings.local_mpp_dir),
                recursive=False,
            )
            observer.start()

            self._observer = observer
            self._thread = threading.Thread(
                target=self._join_observer,
                name="mpp-watcher",
                daemon=True,
            )
            self._thread.start()

        logger.info("Watcher iniciado. Pasta observada: %s", self._settings.local_mpp_dir)

    def stop(self) -> None:
        """Para o watcher e aguarda a thread encerrar."""
        with self._lock:
            observer = self._observer
            thread = self._thread
            self._observer = None
            self._thread = None

        if observer is None:
            return

        observer.stop()
        observer.join()
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)
        logger.info("Watcher encerrado.")

    def _join_observer(self) -> None:
        observer = self._observer
        if observer is None:
            return
        while observer.is_alive():
            observer.join(timeout=1)


def main() -> None:
    """Ponto de entrada do script."""
    from gui import App

    App().run()


if __name__ == "__main__":
    main()
