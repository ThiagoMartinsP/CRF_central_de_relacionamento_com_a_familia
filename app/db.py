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


VERSAO_SCHEMA = 2


def inicializar(con: sqlite3.Connection) -> None:
    con.executescript(CAMINHO_SCHEMA.read_text(encoding="utf-8"))
    _migra(con)


def _colunas(con: sqlite3.Connection, tabela: str) -> set[str]:
    return {linha["name"] for linha in con.execute(f"PRAGMA table_info({tabela})")}


def _migra(con: sqlite3.Connection) -> None:
    """Evolui bancos criados por uma versao anterior do schema.

    O gatilho e' a presenca da coluna, nao `user_version`: bancos criados antes
    de existir versionamento tem `user_version = 0` mesmo estando atualizados.
    """
    if "ultima_resposta_em" not in _colunas(con, "conversa_captura"):
        _migra_1_para_2(con)
    con.execute(f"PRAGMA user_version = {VERSAO_SCHEMA}")


def _migra_1_para_2(con: sqlite3.Connection) -> None:
    """Adiciona controle de expiracao em `conversa_captura`.

    Exige reconstruir a tabela: SQLite nao permite alterar um CHECK existente,
    e `status` precisa passar a aceitar 'EXPIRADA'. As sessoes existentes
    herdam `atualizado_em` como `ultima_resposta_em` - aproximacao aceitavel,
    porque antes desta versao nada mais mexia na linha.
    """
    con.executescript(
        """
        PRAGMA foreign_keys = OFF;
        BEGIN;
        ALTER TABLE conversa_captura RENAME TO _conversa_captura_v1;
        DROP INDEX IF EXISTS ux_captura_ativa;

        CREATE TABLE conversa_captura (
          id                   TEXT PRIMARY KEY,
          id_responsavel       TEXT NOT NULL REFERENCES responsavel(id),
          cpf_crianca          TEXT NOT NULL REFERENCES crianca(cpf),
          indice_contato       INTEGER NOT NULL CHECK (indice_contato IN (1, 2)),
          etapa                TEXT NOT NULL DEFAULT 'NOME'
                                 CHECK (etapa IN ('NOME', 'PARENTESCO', 'TELEFONE', 'CONFIRMAR_PROXIMO')),
          dados_parciais       TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(dados_parciais)),
          status               TEXT NOT NULL DEFAULT 'EM_ANDAMENTO'
                                 CHECK (status IN ('EM_ANDAMENTO', 'CONCLUIDA', 'EXPIRADA')),
          ultima_resposta_em   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
          lembrete_enviado_em  TEXT,
          criado_em            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
          atualizado_em        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );

        INSERT INTO conversa_captura (id, id_responsavel, cpf_crianca,
            indice_contato, etapa, dados_parciais, status, ultima_resposta_em,
            lembrete_enviado_em, criado_em, atualizado_em)
        SELECT id, id_responsavel, cpf_crianca, indice_contato, etapa,
               dados_parciais, status, atualizado_em, NULL, criado_em, atualizado_em
        FROM _conversa_captura_v1;

        DROP TABLE _conversa_captura_v1;

        CREATE UNIQUE INDEX ux_captura_ativa ON conversa_captura (id_responsavel)
          WHERE status = 'EM_ANDAMENTO';
        COMMIT;
        PRAGMA foreign_keys = ON;
        """
    )


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
