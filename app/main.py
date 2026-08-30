"""Endpoints do MVP (secao 4 da especificacao)."""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import captura, db


@asynccontextmanager
async def lifespan(app: FastAPI):
    con = db.conectar()
    try:
        db.inicializar(con)
    finally:
        con.close()
    yield


app = FastAPI(
    title="CRF - Captura de Contatos de Apoio (MVP T0)",
    description=(
        "Recorte de captura: inscricao do matricula.rio -> conversa guiada no "
        "WhatsApp -> contatos de apoio ancorados na crianca."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


def obter_conexao():
    con = db.conectar()
    try:
        yield con
    finally:
        con.close()


Conexao = Annotated[sqlite3.Connection, Depends(obter_conexao)]


def _erro(e: captura.ErroDominio) -> HTTPException:
    return HTTPException(status_code=e.status, detail={"codigo": e.codigo, "mensagem": e.detalhe})


class InscricaoEntrada(BaseModel):
    codigo_inscricao: str = Field(min_length=1)
    # str | int: se o CPF chegar como numero no JSON, o normalizador recupera
    # os zeros a esquerda em vez de deixar passar um valor de 10 digitos.
    crianca_cpf: str | int | None = None
    crianca_nome: str = Field(min_length=1)
    responsavel_nome: str = Field(min_length=1)
    responsavel_telefone: str = Field(min_length=1)


class MensagemEntrada(BaseModel):
    telefone_e164: str = Field(min_length=1)
    texto: str = ""


@app.post("/webhooks/matricula-rio")
def webhook_matricula_rio(payload: InscricaoEntrada, con: Conexao):
    """Simula o passo 1: a inscricao chega no CRF."""
    try:
        with db.transacao(con):
            return captura.processar_inscricao(con, **payload.model_dump())
    except captura.ErroDominio as e:
        raise _erro(e) from None


@app.post("/webhooks/whatsapp/inbound")
def webhook_whatsapp_inbound(payload: MensagemEntrada, con: Conexao):
    """Simula o passo 3: a familia responde."""
    with db.transacao(con):
        return captura.processar_mensagem_recebida(con, **payload.model_dump())


@app.post("/manutencao/varrer-sessoes")
def varrer_sessoes(con: Conexao):
    """Aplica lembrete e expiracao as sessoes silenciosas (seção 8.4).

    Idempotente e sem estado proprio: pode ser chamado por Agendador de
    Tarefas / cron na frequencia que fizer sentido, ou na mao durante a demo.
    Nao existe worker em background de proposito - o briefing adiou a
    complexidade de polling para a fase de convocacao.
    """
    with db.transacao(con):
        resumo = captura.varrer_sessoes(con)
    return {
        "prazos_minutos": {
            "lembrete": captura.LEMBRETE_APOS_MIN,
            "expiracao": captura.EXPIRA_APOS_MIN,
        },
        **resumo,
    }


@app.get("/criancas/{cpf}")
def obter_crianca(cpf: str, con: Conexao):
    """Consulta de depuracao: arvore de contato de uma crianca."""
    try:
        return captura.consultar_crianca(con, cpf)
    except captura.ErroDominio as e:
        raise _erro(e) from None


@app.get("/healthz")
def healthz():
    return {"status": "ok", "banco": str(db.caminho_banco())}
