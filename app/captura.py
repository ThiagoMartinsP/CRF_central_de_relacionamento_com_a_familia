"""Regra de disparo (secao 5) e maquina de estados da captura guiada (secao 6)."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid

from . import validadores as v
from .mensageria import enviar, registrar_recebida

VALIDA_DV_CPF = os.environ.get("CRF_VALIDAR_DV_CPF", "1") not in ("0", "false", "False")


class ErroDominio(Exception):
    def __init__(self, status: int, codigo: str, detalhe: str) -> None:
        super().__init__(detalhe)
        self.status = status
        self.codigo = codigo
        self.detalhe = detalhe


# ------------------------------------------------------------------ helpers


def _agora_sql() -> str:
    return "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"


def _nome_crianca(con: sqlite3.Connection, cpf: str) -> str:
    linha = con.execute("SELECT nome FROM crianca WHERE cpf = ?", (cpf,)).fetchone()
    return linha["nome"] if linha else cpf


def _sessao_ativa_do_responsavel(
    con: sqlite3.Connection, id_responsavel: str
) -> sqlite3.Row | None:
    return con.execute(
        "SELECT * FROM conversa_captura "
        "WHERE id_responsavel = ? AND status = 'EM_ANDAMENTO'",
        (id_responsavel,),
    ).fetchone()


def _conta_contatos(con: sqlite3.Connection, cpf: str) -> int:
    return con.execute(
        "SELECT COUNT(*) AS n FROM contato_apoio WHERE cpf_crianca = ?", (cpf,)
    ).fetchone()["n"]


def _abre_sessao(
    con: sqlite3.Connection, id_responsavel: str, cpf_crianca: str
) -> sqlite3.Row:
    """Abre sessao na etapa NOME.

    Desvio consciente da secao 5, que fixa `indice_contato = 1`: derivamos do
    numero de contatos ja gravados. Se a crianca ficou com 1 contato (familia
    respondeu NAO) e a inscricao e' reenviada, `indice = 1` faria a captura
    perguntar "quer cadastrar mais um?" depois do 2o contato e o proximo INSERT
    bateria no trigger. Como `total < 2` e' garantido por quem chama, o valor
    derivado sempre cai no CHECK (1, 2).
    """
    indice = _conta_contatos(con, cpf_crianca) + 1
    id_sessao = str(uuid.uuid4())
    con.execute(
        "INSERT INTO conversa_captura (id, id_responsavel, cpf_crianca, "
        "indice_contato, etapa) VALUES (?, ?, ?, ?, 'NOME')",
        (id_sessao, id_responsavel, cpf_crianca, indice),
    )
    return con.execute(
        "SELECT * FROM conversa_captura WHERE id = ?", (id_sessao,)
    ).fetchone()


def _atualiza_sessao(con: sqlite3.Connection, id_sessao: str, **campos) -> None:
    if "dados_parciais" in campos and not isinstance(campos["dados_parciais"], str):
        campos["dados_parciais"] = json.dumps(
            campos["dados_parciais"], ensure_ascii=False
        )
    atribuicoes = ", ".join(f"{c} = ?" for c in campos)
    con.execute(
        f"UPDATE conversa_captura SET {atribuicoes}, atualizado_em = {_agora_sql()} "
        "WHERE id = ?",
        (*campos.values(), id_sessao),
    )


# ------------------------------------------------- secao 5: regra de disparo


def _upsert_responsavel(con: sqlite3.Connection, telefone: str, nome: str) -> sqlite3.Row:
    con.execute(
        "INSERT INTO responsavel (id, nome, telefone_e164) VALUES (?, ?, ?) "
        "ON CONFLICT (telefone_e164) DO UPDATE SET nome = excluded.nome",
        (str(uuid.uuid4()), nome, telefone),
    )
    return con.execute(
        "SELECT * FROM responsavel WHERE telefone_e164 = ?", (telefone,)
    ).fetchone()


def processar_inscricao(
    con: sqlite3.Connection,
    *,
    codigo_inscricao: str,
    crianca_cpf: object,
    crianca_nome: str,
    responsavel_nome: str,
    responsavel_telefone: str,
) -> dict:
    cpf = v.normaliza_cpf(crianca_cpf)
    if cpf is None:
        raise ErroDominio(
            422, "CPF_CRIANCA_INVALIDO",
            "crianca_cpf ausente ou fora do formato de 11 digitos (secao 8.3: "
            "sem CPF, sem cadastro)",
        )
    if VALIDA_DV_CPF and not v.cpf_dv_valido(cpf):
        raise ErroDominio(
            422, "CPF_CRIANCA_DV_INVALIDO",
            f"digito verificador do CPF {cpf} nao fecha",
        )

    telefone = v.normaliza_e164_brasil(responsavel_telefone)
    if telefone is None:
        raise ErroDominio(
            422, "TELEFONE_RESPONSAVEL_INVALIDO",
            f"responsavel_telefone {responsavel_telefone!r} nao e' um celular "
            "brasileiro valido",
        )

    # O codigo de inscricao e' UNIQUE e independente do CPF: se ja pertence a
    # outra crianca, o payload esta inconsistente e nao ha upsert possivel.
    dono = con.execute(
        "SELECT cpf FROM crianca WHERE codigo_inscricao = ?", (codigo_inscricao,)
    ).fetchone()
    if dono and dono["cpf"] != cpf:
        raise ErroDominio(
            409, "CODIGO_INSCRICAO_EM_USO",
            f"codigo_inscricao {codigo_inscricao} ja pertence a outra crianca",
        )

    responsavel = _upsert_responsavel(con, telefone, responsavel_nome)

    existente = con.execute("SELECT * FROM crianca WHERE cpf = ?", (cpf,)).fetchone()
    if existente is None:
        con.execute(
            "INSERT INTO crianca (cpf, id_responsavel, nome, codigo_inscricao) "
            "VALUES (?, ?, ?, ?)",
            (cpf, responsavel["id"], crianca_nome, codigo_inscricao),
        )
        crianca_criada = True
    else:
        # Upsert por CPF: reenvio da mesma inscricao nao duplica nem reabre a
        # captura. Preservamos o codigo_inscricao original de proposito.
        con.execute(
            "UPDATE crianca SET nome = ?, id_responsavel = ? WHERE cpf = ?",
            (crianca_nome, responsavel["id"], cpf),
        )
        crianca_criada = False

    resultado: dict = {
        "responsavel": {
            "id": responsavel["id"],
            "nome": responsavel["nome"],
            "telefone_e164": responsavel["telefone_e164"],
        },
        "crianca": {"cpf": cpf, "nome": crianca_nome, "criada": crianca_criada},
        "mensagens": [],
    }

    total_contatos = _conta_contatos(con, cpf)
    ja_capturando_esta_crianca = con.execute(
        "SELECT 1 FROM conversa_captura "
        "WHERE cpf_crianca = ? AND status = 'EM_ANDAMENTO'",
        (cpf,),
    ).fetchone() is not None
    sessao_do_responsavel = _sessao_ativa_do_responsavel(con, responsavel["id"])

    if total_contatos >= 2 or ja_capturando_esta_crianca:
        resultado["acao"] = "NENHUMA"
        resultado["motivo"] = (
            "crianca ja tem 2 contatos de apoio"
            if total_contatos >= 2
            else "captura desta crianca ja esta em andamento"
        )
        return resultado

    if sessao_do_responsavel is not None:
        # Secao 8.2: o responsavel esta no meio da captura de outra crianca.
        # Enfileira e nao manda mensagem agora. INSERT OR IGNORE porque
        # captura_pendente.cpf_crianca e' UNIQUE (reenvio do webhook).
        con.execute(
            "INSERT OR IGNORE INTO captura_pendente (id, id_responsavel, cpf_crianca) "
            "VALUES (?, ?, ?)",
            (str(uuid.uuid4()), responsavel["id"], cpf),
        )
        resultado["acao"] = "ENFILEIRADA"
        resultado["motivo"] = (
            "responsavel ocupado com a captura da crianca "
            f"{sessao_do_responsavel['cpf_crianca']}"
        )
        return resultado

    sessao = _abre_sessao(con, responsavel["id"], cpf)
    resultado["mensagens"].append(
        enviar(
            con,
            responsavel["id"],
            "M1_BOAS_VINDAS_PEDE_CONTATO",
            nome=responsavel["nome"],
            crianca=crianca_nome,
        )
    )
    resultado["acao"] = "CAPTURA_INICIADA"
    resultado["sessao"] = {"id": sessao["id"], "indice_contato": sessao["indice_contato"]}
    return resultado


# ---------------------------------- secao 6.2: encerramento + drenagem da fila


def encerrar_sessao(con: sqlite3.Connection, sessao: sqlite3.Row) -> list[dict]:
    mensagens: list[dict] = []
    _atualiza_sessao(con, sessao["id"], status="CONCLUIDA")
    mensagens.append(
        enviar(
            con,
            sessao["id_responsavel"],
            "M1_ENCERRAMENTO",
            crianca=_nome_crianca(con, sessao["cpf_crianca"]),
        )
    )

    proxima = con.execute(
        "SELECT * FROM captura_pendente WHERE id_responsavel = ? "
        "ORDER BY criado_em, id LIMIT 1",
        (sessao["id_responsavel"],),
    ).fetchone()
    if proxima is None:
        return mensagens

    con.execute("DELETE FROM captura_pendente WHERE id = ?", (proxima["id"],))
    _abre_sessao(con, sessao["id_responsavel"], proxima["cpf_crianca"])
    mensagens.append(
        enviar(
            con,
            sessao["id_responsavel"],
            "M1_PEDE_CONTATO_PROXIMA_CRIANCA",
            crianca=_nome_crianca(con, proxima["cpf_crianca"]),
        )
    )
    return mensagens


# ------------------------------------- secao 6.1: webhook inbound do WhatsApp


def _grava_contato(
    con: sqlite3.Connection, sessao: sqlite3.Row, telefone: str
) -> tuple[dict | None, str | None]:
    """Insere em contato_apoio. Devolve (contato, codigo_de_erro)."""
    dados = json.loads(sessao["dados_parciais"])
    id_contato = str(uuid.uuid4())
    try:
        con.execute(
            "INSERT INTO contato_apoio (id, cpf_crianca, nome, grau_relacao, "
            "telefone_e164) VALUES (?, ?, ?, ?, ?)",
            (
                id_contato,
                sessao["cpf_crianca"],
                dados["nome"],
                dados["grau_relacao"],
                telefone,
            ),
        )
    except sqlite3.IntegrityError as erro:
        # RAISE(ABORT) e violacao de UNIQUE desfazem apenas o statement; a
        # transacao segue viva, entao podemos responder a familia normalmente.
        texto = str(erro)
        if "CRF_MAX_CONTATOS_APOIO" in texto:
            return None, "LIMITE"
        if "UNIQUE" in texto:
            return None, "DUPLICADO"
        raise
    return (
        {
            "id": id_contato,
            "nome": dados["nome"],
            "grau_relacao": dados["grau_relacao"],
            "telefone_e164": telefone,
        },
        None,
    )


def processar_mensagem_recebida(
    con: sqlite3.Connection, *, telefone_e164: str, texto: str
) -> dict:
    telefone = v.normaliza_e164_brasil(telefone_e164) or telefone_e164
    responsavel = con.execute(
        "SELECT * FROM responsavel WHERE telefone_e164 = ?", (telefone,)
    ).fetchone()
    if responsavel is None:
        return {"acao": "IGNORADA_NUMERO_DESCONHECIDO", "mensagens": []}

    sessao = _sessao_ativa_do_responsavel(con, responsavel["id"])
    if sessao is None:
        return {"acao": "IGNORADA_SEM_SESSAO_ABERTA", "mensagens": []}

    registrar_recebida(con, responsavel["id"], texto)

    nome_crianca = _nome_crianca(con, sessao["cpf_crianca"])
    dados = json.loads(sessao["dados_parciais"])
    mensagens: list[dict] = []
    resultado: dict = {
        "etapa_anterior": sessao["etapa"],
        "indice_contato": sessao["indice_contato"],
        "cpf_crianca": sessao["cpf_crianca"],
        "contato_gravado": None,
    }
    etapa = sessao["etapa"]

    if etapa == "NOME":
        if not (texto or "").strip():
            mensagens.append(
                enviar(con, responsavel["id"], "ERRO_NOME_VAZIO")
            )
            resultado["acao"] = "REPETE_ETAPA"
        else:
            dados["nome"] = texto.strip()
            _atualiza_sessao(
                con, sessao["id"], etapa="PARENTESCO", dados_parciais=dados
            )
            mensagens.append(
                enviar(
                    con, responsavel["id"], "M1_PEDE_PARENTESCO",
                    nome_contato=dados["nome"],
                )
            )
            resultado["acao"] = "AVANCOU"

    elif etapa == "PARENTESCO":
        dados["grau_relacao"] = v.normaliza_grau_relacao(texto)
        _atualiza_sessao(con, sessao["id"], etapa="TELEFONE", dados_parciais=dados)
        mensagens.append(
            enviar(
                con, responsavel["id"], "M1_PEDE_TELEFONE",
                nome_contato=dados.get("nome", ""),
            )
        )
        resultado["acao"] = "AVANCOU"

    elif etapa == "TELEFONE":
        normalizado = v.normaliza_e164_brasil(texto)
        if normalizado is None:
            mensagens.append(
                enviar(con, responsavel["id"], "ERRO_TELEFONE_INVALIDO")
            )
            resultado["acao"] = "REPETE_ETAPA"
        else:
            contato, erro = _grava_contato(con, sessao, normalizado)
            if erro == "DUPLICADO":
                mensagens.append(
                    enviar(
                        con, responsavel["id"], "ERRO_TELEFONE_DUPLICADO",
                        crianca=nome_crianca,
                    )
                )
                resultado["acao"] = "REPETE_ETAPA"
            elif erro == "LIMITE":
                mensagens.append(
                    enviar(
                        con, responsavel["id"], "ERRO_LIMITE_CONTATOS",
                        crianca=nome_crianca,
                    )
                )
                _atualiza_sessao(con, sessao["id"], status="CONCLUIDA")
                resultado["acao"] = "SESSAO_ENCERRADA_POR_LIMITE"
            else:
                resultado["contato_gravado"] = contato
                _atualiza_sessao(con, sessao["id"], etapa="CONFIRMAR_PROXIMO")
                if sessao["indice_contato"] == 1:
                    mensagens.append(
                        enviar(
                            con, responsavel["id"], "M1_PERGUNTA_SEGUNDO",
                            crianca=nome_crianca,
                        )
                    )
                    resultado["acao"] = "CONTATO_GRAVADO"
                else:
                    atual = con.execute(
                        "SELECT * FROM conversa_captura WHERE id = ?", (sessao["id"],)
                    ).fetchone()
                    mensagens.extend(encerrar_sessao(con, atual))
                    resultado["acao"] = "CONTATO_GRAVADO_E_SESSAO_ENCERRADA"

    elif etapa == "CONFIRMAR_PROXIMO":
        if v.normaliza_sim_nao(texto) == "SIM" and sessao["indice_contato"] == 1:
            _atualiza_sessao(con, sessao["id"], status="CONCLUIDA")
            con.execute(
                "INSERT INTO conversa_captura (id, id_responsavel, cpf_crianca, "
                "indice_contato, etapa) VALUES (?, ?, ?, 2, 'NOME')",
                (str(uuid.uuid4()), responsavel["id"], sessao["cpf_crianca"]),
            )
            mensagens.append(
                enviar(
                    con, responsavel["id"], "M1_PEDE_NOME_SEGUNDO",
                    crianca=nome_crianca,
                )
            )
            resultado["acao"] = "SEGUNDO_CONTATO_INICIADO"
        else:
            mensagens.extend(encerrar_sessao(con, sessao))
            resultado["acao"] = "SESSAO_ENCERRADA"

    resultado["mensagens"] = mensagens
    atual = con.execute(
        "SELECT etapa, status FROM conversa_captura WHERE id = ?", (sessao["id"],)
    ).fetchone()
    resultado["etapa_atual"] = atual["etapa"]
    resultado["status_sessao"] = atual["status"]
    return resultado


# ------------------------------------------- secao 4.3: consulta de depuracao


def consultar_crianca(con: sqlite3.Connection, cpf_bruto: object) -> dict:
    cpf = v.normaliza_cpf(cpf_bruto)
    if cpf is None:
        raise ErroDominio(422, "CPF_INVALIDO", "cpf fora do formato de 11 digitos")

    crianca = con.execute("SELECT * FROM crianca WHERE cpf = ?", (cpf,)).fetchone()
    if crianca is None:
        raise ErroDominio(404, "CRIANCA_NAO_ENCONTRADA", f"crianca {cpf} nao cadastrada")

    responsavel = con.execute(
        "SELECT * FROM responsavel WHERE id = ?", (crianca["id_responsavel"],)
    ).fetchone()
    contatos = con.execute(
        "SELECT nome, grau_relacao, telefone_e164, criado_em FROM contato_apoio "
        "WHERE cpf_crianca = ? ORDER BY criado_em, id",
        (cpf,),
    ).fetchall()
    sessao = con.execute(
        "SELECT id, indice_contato, etapa, dados_parciais, status FROM conversa_captura "
        "WHERE cpf_crianca = ? AND status = 'EM_ANDAMENTO'",
        (cpf,),
    ).fetchone()
    na_fila = con.execute(
        "SELECT 1 FROM captura_pendente WHERE cpf_crianca = ?", (cpf,)
    ).fetchone() is not None

    return {
        "crianca": {
            "cpf": crianca["cpf"],
            "nome": crianca["nome"],
            "codigo_inscricao": crianca["codigo_inscricao"],
            "criado_em": crianca["criado_em"],
        },
        "responsavel": {
            "id": responsavel["id"],
            "nome": responsavel["nome"],
            "telefone_e164": responsavel["telefone_e164"],
        },
        "contatos_apoio": [dict(c) for c in contatos],
        "captura": {
            "sessao_ativa": (
                {
                    "id": sessao["id"],
                    "indice_contato": sessao["indice_contato"],
                    "etapa": sessao["etapa"],
                    "dados_parciais": json.loads(sessao["dados_parciais"]),
                }
                if sessao
                else None
            ),
            "aguardando_na_fila": na_fila,
        },
    }
