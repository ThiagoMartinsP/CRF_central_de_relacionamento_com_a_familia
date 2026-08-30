"""Camada de "envio" de WhatsApp.

Nao ha adapter de provedor neste recorte (secao 10): enviar significa gravar em
`mensagem` e devolver o texto renderizado, que os endpoints retornam no corpo
da resposta para a demo poder exibir a conversa.
"""

from __future__ import annotations

import sqlite3
import uuid

from .templates import renderiza

_SQL_INSERE = """
INSERT INTO mensagem (id, id_responsavel, direcao, conteudo, template_usado,
                      id_mensagem_externa)
VALUES (?, ?, ?, ?, ?, ?)
"""


def enviar(
    con: sqlite3.Connection,
    id_responsavel: str,
    template: str,
    **contexto: str,
) -> dict:
    conteudo = renderiza(template, **contexto)
    id_externo = f"sim-{uuid.uuid4().hex[:12]}"
    con.execute(
        _SQL_INSERE,
        (str(uuid.uuid4()), id_responsavel, "ENVIADA", conteudo, template, id_externo),
    )
    return {
        "template": template,
        "conteudo": conteudo,
        "id_mensagem_externa": id_externo,
    }


def registrar_recebida(
    con: sqlite3.Connection, id_responsavel: str, texto: str
) -> None:
    con.execute(
        _SQL_INSERE,
        (str(uuid.uuid4()), id_responsavel, "RECEBIDA", texto, None, None),
    )