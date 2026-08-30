"""Demo CLI: dispara o webhook do matricula.rio e simula as respostas da familia.

Por padrao roda a aplicacao em processo (TestClient), sem precisar de servidor.
Para bater num servidor ja de pe:

    uv run uvicorn app.main:app --reload
    uv run python scripts/demo.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import warnings
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.validadores import gera_cpf_valido  # noqa: E402

BANCO_DEMO = RAIZ / "crf_demo.db"

TEL_MARIA = "+5521999990001"
TEL_DESCONHECIDO = "+5521912340000"
CPF_ANA = gera_cpf_valido("529982247")     # CPF sintetico com DV valido
CPF_BRUNO = gera_cpf_valido("012345678")   # comeca com 0: prova que o zero sobrevive


# ------------------------------------------------------------------ impressao

LARGURA = 78


def titulo(texto: str) -> None:
    print("\n" + "=" * LARGURA)
    print(texto)
    print("=" * LARGURA)


def passo(texto: str) -> None:
    print(f"\n-- {texto}")


def bot(mensagens: list[dict]) -> None:
    for m in mensagens:
        print(f"   CRF  [{m['template']}]")
        for linha in _quebra(m["conteudo"]):
            print(f"        {linha}")


def familia(texto: str) -> None:
    print(f"   FAM  > {texto!r}")


def _quebra(texto: str, largura: int = 68) -> list[str]:
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        if len(atual) + len(p) + 1 > largura:
            linhas.append(atual)
            atual = p
        else:
            atual = f"{atual} {p}".strip()
    if atual:
        linhas.append(atual)
    return linhas


# ------------------------------------------------------------------ chamadas


class Api:
    def __init__(self, cliente) -> None:
        self.c = cliente

    def inscricao(self, **payload):
        r = self.c.post("/webhooks/matricula-rio", json=payload)
        corpo = r.json()
        if r.status_code >= 400:
            print(f"   HTTP {r.status_code}  {corpo['detail']['codigo']}: "
                  f"{corpo['detail']['mensagem']}")
            return corpo
        print(f"   HTTP {r.status_code}  acao={corpo['acao']}"
              + (f"  motivo={corpo['motivo']}" if corpo.get("motivo") else ""))
        bot(corpo["mensagens"])
        return corpo

    def responde(self, telefone: str, texto: str):
        familia(texto)
        r = self.c.post(
            "/webhooks/whatsapp/inbound",
            json={"telefone_e164": telefone, "texto": texto},
        )
        corpo = r.json()
        detalhe = f"acao={corpo['acao']}"
        if corpo.get("etapa_anterior"):
            detalhe += f"  {corpo['etapa_anterior']} -> {corpo['etapa_atual']}"
        if corpo.get("status_sessao"):
            detalhe += f"  sessao={corpo['status_sessao']}"
        print(f"        ({detalhe})")
        if corpo.get("contato_gravado"):
            c = corpo["contato_gravado"]
            print(f"        [DB] contato_apoio += {c['nome']} / "
                  f"{c['grau_relacao']} / {c['telefone_e164']}")
        bot(corpo["mensagens"])
        return corpo

    def crianca(self, cpf: str):
        r = self.c.get(f"/criancas/{cpf}")
        corpo = r.json()
        if r.status_code >= 400:
            print(f"   HTTP {r.status_code}  {corpo['detail']}")
            return corpo
        print(f"   crianca      {corpo['crianca']['nome']}  "
              f"cpf={corpo['crianca']['cpf']}  "
              f"inscricao={corpo['crianca']['codigo_inscricao']}")
        print(f"   responsavel  {corpo['responsavel']['nome']}  "
              f"{corpo['responsavel']['telefone_e164']}")
        if corpo["contatos_apoio"]:
            for i, c in enumerate(corpo["contatos_apoio"], 1):
                print(f"   apoio #{i}     {c['nome']}  ({c['grau_relacao']})  "
                      f"{c['telefone_e164']}")
        else:
            print("   apoio        (nenhum)")
        cap = corpo["captura"]
        ativa = cap["sessao_ativa"]
        print(f"   captura      sessao_ativa="
              f"{ativa['etapa'] + '/idx' + str(ativa['indice_contato']) if ativa else 'nenhuma'}"
              f"  na_fila={cap['aguardando_na_fila']}")
        return corpo


# ------------------------------------------------------------------ cenarios


def roda(api: Api) -> None:
    titulo("CENARIO 1 - Inscricao chega do matricula.rio (passo 1)")
    passo("POST /webhooks/matricula-rio  (Ana Silva)")
    api.inscricao(
        codigo_inscricao="INSC-2026-000123",
        crianca_cpf=CPF_ANA,
        crianca_nome="Ana Silva",
        responsavel_nome="Maria Silva",
        responsavel_telefone="(21) 99999-0001",
    )

    titulo("CENARIO 2 - Segunda inscricao com a captura aberta (secao 8.2)")
    passo("POST /webhooks/matricula-rio  (Bruno Silva, mesma responsavel)")
    print(f"   CPF de Bruno = {CPF_BRUNO}  (comeca com zero, de proposito)")
    api.inscricao(
        codigo_inscricao="INSC-2026-000124",
        crianca_cpf=CPF_BRUNO,
        crianca_nome="Bruno Silva",
        responsavel_nome="Maria Silva",
        responsavel_telefone=TEL_MARIA,
    )
    print("   -> nao mandou mensagem: entrou em captura_pendente")

    titulo("CENARIO 3 - Captura guiada da Ana, campo a campo (secao 6)")
    api.responde(TEL_MARIA, "Joana Souza")
    api.responde(TEL_MARIA, "vovó")
    passo("resposta fora de formato (secao 8.5): nao avanca de etapa")
    api.responde(TEL_MARIA, "nao lembro")
    api.responde(TEL_MARIA, "(21) 98888-1234")
    passo("familia aceita cadastrar o segundo contato")
    api.responde(TEL_MARIA, "sim")
    api.responde(TEL_MARIA, "Carlos Pereira")
    api.responde(TEL_MARIA, "vizinho")
    passo("telefone repetido: barrado por UNIQUE (cpf_crianca, telefone_e164)")
    api.responde(TEL_MARIA, "21988881234")
    api.responde(TEL_MARIA, "21 97777-5555")
    print("   -> 2o contato fecha a sessao e a fila destrava sozinha (secao 6.2)")

    titulo("CENARIO 4 - Captura do Bruno, iniciada pela fila")
    api.responde(TEL_MARIA, "Joana Souza")
    api.responde(TEL_MARIA, "avó")
    api.responde(TEL_MARIA, "+55 21 98888-1234")
    print("   -> mesmo telefone da Ana e' aceito aqui: a arvore e' por crianca")
    passo("familia diz que nao quer o segundo contato")
    api.responde(TEL_MARIA, "não")

    titulo("CENARIO 5 - Arvore de contato de cada crianca (GET /criancas/:cpf)")
    passo(f"GET /criancas/{CPF_ANA}")
    api.crianca(CPF_ANA)
    passo(f"GET /criancas/{CPF_BRUNO}")
    api.crianca(CPF_BRUNO)

    titulo("CENARIO 6 - Rejeicoes e no-ops")
    passo("inscricao sem CPF (secao 8.3) -> 422, nada e' criado")
    api.inscricao(
        codigo_inscricao="INSC-2026-000199",
        crianca_nome="Sem Cpf",
        responsavel_nome="Fulana",
        responsavel_telefone="+5521999990009",
    )
    passo("CPF com digito verificador errado -> 422")
    api.inscricao(
        codigo_inscricao="INSC-2026-000200",
        crianca_cpf="11122233399",
        crianca_nome="Dv Errado",
        responsavel_nome="Fulana",
        responsavel_telefone="+5521999990009",
    )
    passo("codigo_inscricao ja usado por outra crianca -> 409")
    api.inscricao(
        codigo_inscricao="INSC-2026-000123",
        crianca_cpf=gera_cpf_valido("111444777"),
        crianca_nome="Outra Crianca",
        responsavel_nome="Fulana",
        responsavel_telefone="+5521999990009",
    )
    passo("reenvio da inscricao da Ana (ja tem 2 contatos) -> acao=NENHUMA")
    api.inscricao(
        codigo_inscricao="INSC-2026-000123",
        crianca_cpf=CPF_ANA,
        crianca_nome="Ana Silva",
        responsavel_nome="Maria Silva",
        responsavel_telefone=TEL_MARIA,
    )
    passo("mensagem de numero nao cadastrado -> ignorada")
    api.responde(TEL_DESCONHECIDO, "oi")
    passo("mensagem sem sessao aberta -> ignorada")
    api.responde(TEL_MARIA, "obrigada!")


def prova_trigger_no_banco(caminho: Path) -> None:
    """Decisao 3: o limite de 2 esta no banco, nao so na aplicacao."""
    titulo("CENARIO 7 - Limite de 2 contatos travado no banco (decisao 3)")
    con = sqlite3.connect(caminho)
    con.execute("PRAGMA foreign_keys = ON")
    passo("INSERT direto de um 3o contato de apoio para a Ana, sem passar pela app")
    try:
        con.execute(
            "INSERT INTO contato_apoio (id, cpf_crianca, nome, grau_relacao, "
            "telefone_e164) VALUES ('x', ?, 'Terceiro', 'amigo', '+5521955550000')",
            (CPF_ANA,),
        )
        print("   FALHOU: o banco aceitou o 3o contato")
    except sqlite3.IntegrityError as erro:
        print(f"   IntegrityError: {erro}")
        print("   -> trigger trg_max_contatos_apoio barrou (equivale ao RAISE do plpgsql)")

    passo("SELECT no CPF do Bruno para confirmar que o zero a esquerda sobreviveu")
    linha = con.execute(
        "SELECT cpf, typeof(cpf) AS tipo, nome FROM crianca WHERE nome = 'Bruno Silva'"
    ).fetchone()
    print(f"   cpf={linha[0]!r}  typeof={linha[1]}  nome={linha[2]}")
    con.close()


def main() -> None:
    # O console do Windows usa cp1252 por padrao no Python 3.13, o que quebra
    # os acentos dos templates.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except AttributeError:
        pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", help="bate num servidor ja rodando")
    ap.add_argument("--manter-banco", action="store_true",
                    help="nao apaga o banco da demo antes de rodar")
    args = ap.parse_args()

    if args.base_url:
        import httpx

        with httpx.Client(base_url=args.base_url, timeout=10) as cliente:
            roda(Api(cliente))
        print("\n(--base-url: cenario 7 exige acesso local ao arquivo do banco)")
        return

    os.environ["CRF_DATABASE"] = str(BANCO_DEMO)
    if not args.manter_banco:
        for sufixo in ("", "-wal", "-shm"):
            Path(str(BANCO_DEMO) + sufixo).unlink(missing_ok=True)

    # starlette 1.6 avisa que prefere httpx2 no TestClient; nao muda nada aqui.
    warnings.filterwarnings("ignore", message=".*httpx2.*")

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as cliente:
        roda(Api(cliente))
    prova_trigger_no_banco(BANCO_DEMO)
    print(f"\nBanco da demo: {BANCO_DEMO}")


if __name__ == "__main__":
    main()
