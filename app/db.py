"""Conexao e inicializacao do banco SQLite."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_SCHEMA = Path(__file__).resolve().parent / "schema.sql"
CAMINHO_PADRAO = RAIZ / "crf.db"


def caminho_banco() -> Path:
    """Arquivo do banco. Sobrescrevivel por CRF_DATABASE (usado pela demo)."""
    return Path(os.environ.get("CRF_DATABASE") or CAMINHO_PADRAO)


def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(caminho_banco(), isolation_level=None)
    con.row_factory = sqlite3.Row
    # SQLite desliga integridade referencial por padrao, e a configuracao e'
    # por conexao - sem isto os REFERENCES do schema nao sao verificados.
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    return con


def inicializar(con: sqlite3.Connection) -> None:
    con.executescript(CAMINHO_SCHEMA.read_text(encoding="utf-8"))


@contextmanager
def transacao(con: sqlite3.Connection):
    """Transacao explicita (a conexao esta em autocommit).

    IMMEDIATE pega o write lock na entrada, evitando SQLITE_BUSY em escrita
    concorrente - o webhook do matricula.rio e o do WhatsApp escrevem nas
    mesmas tabelas.
    """
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    con.execute("COMMIT")
