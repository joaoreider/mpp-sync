"""Schema de custos na tabela tarefas."""

from sqlalchemy import inspect, text

from models import _engine_cache, get_engine, init_db

_COST_COLUMNS = ("custo", "numero_linha_base", "custo_real", "custo_projetado")


def _url(path) -> str:
    return f"sqlite:///{path}"


def _forget(url: str) -> None:
    _engine_cache.pop(url, None)


def test_init_db_creates_only_tarefas_with_cost_columns(tmp_path):
    url = _url(tmp_path / "fresh.db")
    _forget(url)

    init_db(url)

    inspector = inspect(get_engine(url))
    tables = set(inspector.get_table_names())
    assert tables == {"tarefas"}
    columns = {
        column["name"]: column for column in inspector.get_columns("tarefas")
    }
    for name in _COST_COLUMNS:
        assert name in columns
        assert columns[name]["nullable"] is False


def test_init_db_drops_timephased_tables_and_incomplete_tarefas(tmp_path):
    url = _url(tmp_path / "legacy.db")
    _forget(url)
    engine = get_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE conjunto_dados_faseados_tarefa (id INTEGER)"))
        connection.execute(text("CREATE TABLE linhas_base_faseadas_tarefa (id INTEGER)"))
        connection.execute(
            text(
                "CREATE TABLE tarefas ("
                "id INTEGER PRIMARY KEY, nome_do_projeto VARCHAR(500))"
            )
        )

    init_db(url)

    inspector = inspect(get_engine(url))
    tables = set(inspector.get_table_names())
    assert "conjunto_dados_faseados_tarefa" not in tables
    assert "linhas_base_faseadas_tarefa" not in tables
    assert "tarefas" in tables
    columns = {column["name"] for column in inspector.get_columns("tarefas")}
    assert set(_COST_COLUMNS) <= columns
