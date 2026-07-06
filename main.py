"""Pipeline ETL: pasta local -> MS Project (.mpp) -> banco relacional."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from config import Settings, load_settings
from models import Projeto, Tarefa, get_session_factory, init_db
from project_parser import (
    PROJECT_FILE_EXTENSION,
    ProjetoDTO,
    TarefaDTO,
    parse_project_file,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


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


def run_pipeline(settings: Settings) -> None:
    """Executa o pipeline completo de ETL."""
    pipeline_start = time.perf_counter()

    db_start = time.perf_counter()
    init_db(settings.database_url)
    session_factory = get_session_factory(settings.database_url)
    logger.info("Banco inicializado em %d ms.", _elapsed_ms(db_start))

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
            with session_factory() as session:
                process_project_file(session, project_path)
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


def main() -> None:
    """Ponto de entrada do script."""
    settings = load_settings()
    run_pipeline(settings)


if __name__ == "__main__":
    main()
