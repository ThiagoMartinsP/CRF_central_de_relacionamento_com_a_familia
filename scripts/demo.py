"""Demo CLI: dispara o webhook do matricula.rio e simula as respostas da familia.

Por padrao mostra um roteiro so: uma inscricao, uma crianca, os dois contatos
de apoio - o caminho que a maioria das familias percorre.

Dois modos de apresentacao:

    uv run python scripts/demo.py --simples     # le como uma conversa de WhatsApp
    uv run python scripts/demo.py               # detalhado, com estado interno

Extras:

    --parte tudo            os 9 cenarios (fila de irmaos, recusas, expiracao)
    --devagar [FATOR]       pausa entre mensagens, para gravar em video
    --pausa                 espera Enter entre as mensagens (bom para apresentar)
    --base-url URL          bate num servidor de pe em vez de rodar em processo
    --manter-banco          nao apaga o banco da demo antes de rodar

Roda a aplicacao em processo (TestClient), sem precisar de servidor nem banco.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.validadores import gera_cpf_valido  # noqa: E402

BANCO_DEMO = RAIZ / "crf_demo.db"

TEL_MARIA = "+5521999990001"
TEL_CARLA = "+5521988880002"
TEL_DESCONHECIDO = "+5521912340000"
CPF_ANA = gera_cpf_valido("529982247")     # CPF sintetico com DV valido
CPF_BRUNO = gera_cpf_valido("012345678")   # comeca com 0: prova que o zero sobrevive
CPF_DUDA = gera_cpf_valido("222333444")
CPF_ELIAS = gera_cpf_valido("333444555")

NOMES = {TEL_MARIA: "Maria", TEL_CARLA: "Carla", TEL_DESCONHECIDO: "Numero novo"}

# Preenchido por main(); controla apenas a apresentacao, nunca o comportamento.
SIMPLES = False
PAUSA = False
RITMO = 0.0   # multiplicador de pausa; 0 = sem pausa nenhuma
LARGURA = 78


# ------------------------------------------------------------------ formatacao


def cpf_bonito(cpf: str) -> str:
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}" if len(cpf) == 11 else cpf


def tel_bonito(e164: str) -> str:
    digitos = e164.lstrip("+")
    if digitos.startswith("55") and len(digitos) == 13:
        return f"({digitos[2:4]}) {digitos[4:9]}-{digitos[9:]}"
    return e164


def _quebra(texto: str, largura: int = 62) -> list[str]:
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


# ------------------------------------------------------------------ impressao


def _espera(texto: str = "") -> None:
    """Ritmo da apresentacao. Nao afeta a aplicacao, so a leitura.

    Com --devagar a pausa e' proporcional ao tamanho do texto, para a demo
    caber numa gravacao de tela: sem isso ela termina em ~1 segundo e as 451
    linhas passam como um borrao.
    """
    if PAUSA:
        try:
            input()
        except EOFError:
            pass
    elif RITMO:
        time.sleep(min(0.45 + len(texto) * 0.016, 4.5) * RITMO)


def cabecalho(tecnico: str, simples: str) -> None:
    print()
    if SIMPLES:
        print("━" * LARGURA)
        print(f"  {simples}")
        print("━" * LARGURA)
    else:
        print("=" * LARGURA)
        print(tecnico)
        print("=" * LARGURA)
    # Respiro maior na virada de capitulo: e' onde quem assiste se reorienta.
    _espera(simples if SIMPLES else tecnico)


def nota(tecnico: str = "", simples: str = "") -> None:
    """Narracao. Cada modo recebe o texto no seu proprio registro."""
    if SIMPLES:
        if simples:
            print()
            for linha in _quebra(simples, 70):
                print(f"  {linha}")
            _espera(simples)
    elif tecnico:
        print(f"\n-- {tecnico}")


def bot(mensagens: list[dict]) -> None:
    for m in mensagens:
        print()
        if SIMPLES:
            print("        ┌─ CRF · Prefeitura do Rio")
            for linha in _quebra(m["conteudo"]):
                print(f"        │ {linha}")
            print("        └" + "─" * 30)
        else:
            print(f"   CRF  [{m['template']}]")
            for linha in _quebra(m["conteudo"], 68):
                print(f"        {linha}")
        _espera(m["conteudo"])


def familia(telefone: str, texto: str) -> None:
    if SIMPLES:
        quem = NOMES.get(telefone, "Familia")
        print()
        print(f"  ┌─ {quem}")
        for linha in _quebra(texto):
            print(f"  │ {linha}")
        print("  └" + "─" * 30)
    else:
        print(f"   FAM  > {texto!r}")
    _espera(texto)


def marca(simbolo: str, texto: str) -> None:
    """Linha de status do modo simples, com recuo continuo."""
    linhas = _quebra(texto, 64)
    print(f"        {simbolo}  {linhas[0]}")
    for linha in linhas[1:]:
        print(f"           {linha}")


def sistema(texto: str) -> None:
    """Marca uma acao do proprio sistema, nao uma mensagem trocada."""
    if SIMPLES:
        marca("⏱", texto)
    else:
        print(f"   [sistema] {texto}")


# ------------------------------------------------------------------ chamadas


class Api:
    def __init__(self, cliente) -> None:
        self.c = cliente

    def inscricao(self, **payload):
        r = self.c.post("/webhooks/matricula-rio", json=payload)
        corpo = r.json()

        if r.status_code >= 400:
            detalhe = corpo["detail"]
            if SIMPLES:
                marca("⚠", f"Inscrição recusada: {_motivo_leigo(detalhe)}")
            else:
                print(f"   HTTP {r.status_code}  {detalhe['codigo']}: {detalhe['mensagem']}")
            return corpo

        if not SIMPLES:
            print(f"   HTTP {r.status_code}  acao={corpo['acao']}"
                  + (f"  motivo={corpo['motivo']}" if corpo.get("motivo") else ""))
        elif corpo["acao"] == "ENFILEIRADA":
            marca("⏱", "Cadastro criado, mas a conversa fica para depois: a "
                       "família ainda está respondendo sobre a outra criança.")
        elif corpo["acao"] == "NENHUMA":
            marca("⏱", "Nada a fazer: essa criança já tem os contatos.")

        bot(corpo.get("manutencao", {}).get("mensagens", []))
        bot(corpo["mensagens"])
        return corpo

    def responde(self, telefone: str, texto: str):
        familia(telefone, texto)
        r = self.c.post(
            "/webhooks/whatsapp/inbound",
            json={"telefone_e164": telefone, "texto": texto},
        )
        corpo = r.json()

        if not SIMPLES:
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
        else:
            if corpo.get("contato_gravado"):
                c = corpo["contato_gravado"]
                marca("✓", f"Contato guardado: {c['nome']} "
                           f"({c['grau_relacao']}) — {tel_bonito(c['telefone_e164'])}")
            if corpo["acao"].startswith("IGNORADA"):
                marca("⏱", "Mensagem ignorada: não havia pergunta em aberto "
                           "para esse número.")

        bot(corpo["mensagens"])
        return corpo

    def varrer(self):
        r = self.c.post("/manutencao/varrer-sessoes")
        corpo = r.json()
        if not SIMPLES:
            print(f"   HTTP {r.status_code}  expiradas={len(corpo['expiradas'])}  "
                  f"lembretes={len(corpo['lembretes'])}")
            for e in corpo["expiradas"]:
                print(f"        [DB] sessao -> EXPIRADA (parou na etapa "
                      f"{e['etapa_em_que_parou']})")
            for lem in corpo["lembretes"]:
                print(f"        [DB] lembrete_enviado_em preenchido (etapa {lem['etapa']})")
        elif not corpo["expiradas"] and not corpo["lembretes"]:
            sistema("Verificação feita: nada vencido, nada a fazer.")
        bot(corpo["mensagens"])
        return corpo

    def crianca(self, cpf: str):
        r = self.c.get(f"/criancas/{cpf}")
        corpo = r.json()
        if r.status_code >= 400:
            print(f"   HTTP {r.status_code}  {corpo['detail']}")
            return corpo

        cap = corpo["captura"]
        ativa = cap["sessao_ativa"]
        if SIMPLES:
            print(f"\n  \U0001f9d2 {corpo['crianca']['nome']}  "
                  f"(CPF {cpf_bonito(corpo['crianca']['cpf'])})")
            print(f"       responsável   {corpo['responsavel']['nome']} — "
                  f"{tel_bonito(corpo['responsavel']['telefone_e164'])}")
            if corpo["contatos_apoio"]:
                for i, c in enumerate(corpo["contatos_apoio"], 1):
                    print(f"       apoio {i}       {c['nome']} ({c['grau_relacao']}) "
                          f"— {tel_bonito(c['telefone_e164'])}")
            else:
                print("       apoio         nenhum contato cadastrado ainda")
            if ativa:
                print("       conversa      em andamento, aguardando resposta")
            elif any(h["status"] == "EXPIRADA" for h in cap["historico_sessoes"]):
                concluida = any(h["status"] == "CONCLUIDA" for h in cap["historico_sessoes"])
                print("       conversa      encerrada"
                      + (" (houve uma tentativa que venceu antes)" if concluida
                         else " por falta de resposta"))
            else:
                print("       conversa      concluída")
            return corpo

        print(f"   crianca      {corpo['crianca']['nome']}  cpf={corpo['crianca']['cpf']}  "
              f"inscricao={corpo['crianca']['codigo_inscricao']}")
        print(f"   responsavel  {corpo['responsavel']['nome']}  "
              f"{corpo['responsavel']['telefone_e164']}")
        if corpo["contatos_apoio"]:
            for i, c in enumerate(corpo["contatos_apoio"], 1):
                print(f"   apoio #{i}     {c['nome']}  ({c['grau_relacao']})  "
                      f"{c['telefone_e164']}")
        else:
            print("   apoio        (nenhum)")
        print(f"   captura      sessao_ativa="
              f"{ativa['etapa'] + '/idx' + str(ativa['indice_contato']) if ativa else 'nenhuma'}"
              f"  na_fila={cap['aguardando_na_fila']}")
        historico = " | ".join(
            f"{h['status']}@{h['etapa']}" for h in cap["historico_sessoes"]
        )
        print(f"   sessoes      {historico or '(nenhuma)'}")
        return corpo


def _motivo_leigo(detalhe: dict) -> str:
    traducoes: dict[str, str] = {
        "CPF_CRIANCA_INVALIDO": "faltou o CPF da criança",
        "CPF_CRIANCA_DV_INVALIDO": "o CPF informado não é um CPF válido",
        "CODIGO_INSCRICAO_EM_USO": "esse número de inscrição já é de outra criança",
    }
    return traducoes.get(detalhe["codigo"]) or str(detalhe["mensagem"])


# ------------------------------------------------------------------ cenarios


def roda_essencial(api: Api) -> None:
    """Roteiro minimo: uma inscricao, uma crianca, os dois contatos de apoio.

    E' o padrao da demo. Sem irmaos, sem fila, sem recusas, sem expiracao - o
    caminho que a maioria das familias percorre, do comeco ao fim. O roteiro
    completo continua disponivel em --parte tudo.
    """
    cabecalho(
        "Inscricao de uma crianca e captura dos contatos de apoio",
        "A inscrição da Ana chega na Prefeitura",
    )
    nota(
        tecnico="POST /webhooks/matricula-rio  (Ana Silva)",
        simples="O matricula.rio informa que a Ana foi inscrita na creche. O "
                "sistema cadastra a criança e puxa conversa no WhatsApp da "
                "mãe, a Maria, pedindo pessoas de confiança para acionar caso "
                "não consigam falar com ela quando a vaga surgir.",
    )
    api.inscricao(
        codigo_inscricao="INSC-2026-000123",
        crianca_cpf=CPF_ANA,
        crianca_nome="Ana Silva",
        responsavel_nome="Maria Silva",
        responsavel_telefone="(21) 99999-0001",
    )

    cabecalho(
        "Captura guiada, um campo por vez",
        "A Maria responde, uma pergunta por vez",
    )
    nota(
        tecnico="etapas NOME -> PARENTESCO -> TELEFONE",
        simples="Nome, parentesco e telefone, nessa ordem. O contato só é "
                "guardado quando o telefone chega válido.",
    )
    api.responde(TEL_MARIA, "Joana Souza")
    api.responde(TEL_MARIA, "vovó")
    api.responde(TEL_MARIA, "(21) 98888-1234")
    nota(
        tecnico="1o contato gravado; etapa CONFIRMAR_PROXIMO",
        simples="Primeiro contato registrado. O sistema oferece um segundo.",
    )
    api.responde(TEL_MARIA, "sim")
    api.responde(TEL_MARIA, "Carlos Pereira")
    api.responde(TEL_MARIA, "vizinho")
    api.responde(TEL_MARIA, "21 97777-5555")

    cabecalho(
        "Arvore de contato resultante (GET /criancas/:cpf)",
        "O que ficou registrado",
    )
    nota(
        tecnico=f"GET /criancas/{CPF_ANA}",
        simples="A Ana entra na fila da creche com três portas para bater, e "
                "não uma: a mãe, a avó e o vizinho.",
    )
    api.crianca(CPF_ANA)


def roda(api: Api) -> None:
    cabecalho(
        "CENARIO 1 - Inscricao chega do matricula.rio (passo 1)",
        "1. A Ana é inscrita na creche",
    )
    nota(
        tecnico="POST /webhooks/matricula-rio  (Ana Silva)",
        simples="A Prefeitura acaba de receber a inscrição da Ana. O sistema "
                "cadastra a criança e puxa conversa no WhatsApp da mãe, a Maria, "
                "pedindo pessoas de confiança para acionar se ela não for "
                "encontrada quando surgir uma vaga.",
    )
    api.inscricao(
        codigo_inscricao="INSC-2026-000123",
        crianca_cpf=CPF_ANA,
        crianca_nome="Ana Silva",
        responsavel_nome="Maria Silva",
        responsavel_telefone="(21) 99999-0001",
    )

    cabecalho(
        "CENARIO 2 - Segunda inscricao com a captura aberta (secao 8.2)",
        "2. O irmão também é inscrito, no meio da conversa",
    )
    nota(
        tecnico="POST /webhooks/matricula-rio  (Bruno Silva, mesma responsavel)",
        simples="Chega a inscrição do Bruno, irmão da Ana, com a mesma mãe. "
                "Como a Maria ainda está respondendo sobre a Ana, o sistema "
                "guarda o Bruno na fila e fica calado: duas conversas ao mesmo "
                "tempo no mesmo WhatsApp deixariam as respostas ambíguas.",
    )
    if not SIMPLES:
        print(f"   CPF de Bruno = {CPF_BRUNO}  (comeca com zero, de proposito)")
    api.inscricao(
        codigo_inscricao="INSC-2026-000124",
        crianca_cpf=CPF_BRUNO,
        crianca_nome="Bruno Silva",
        responsavel_nome="Maria Silva",
        responsavel_telefone=TEL_MARIA,
    )

    cabecalho(
        "CENARIO 3 - Captura guiada da Ana, campo a campo (secao 6)",
        "3. A Maria responde, uma pergunta por vez",
    )
    nota(simples="O sistema pergunta um campo por vez: nome, parentesco e "
                 "telefone. Nada é guardado até o telefone chegar válido.")
    api.responde(TEL_MARIA, "Joana Souza")
    api.responde(TEL_MARIA, "vovó")
    nota(
        tecnico="resposta fora de formato (secao 8.5): nao avanca de etapa",
        simples="Agora a Maria responde algo que não é telefone. O sistema "
                "insiste na mesma pergunta em vez de seguir adiante — "
                "contato sem telefone não serve para nada.",
    )
    api.responde(TEL_MARIA, "nao lembro")
    api.responde(TEL_MARIA, "(21) 98888-1234")
    nota(
        tecnico="familia aceita cadastrar o segundo contato",
        simples="Primeiro contato guardado. A Maria aceita cadastrar um segundo.",
    )
    api.responde(TEL_MARIA, "sim")
    api.responde(TEL_MARIA, "Carlos Pereira")
    api.responde(TEL_MARIA, "vizinho")
    nota(
        tecnico="telefone repetido: barrado por UNIQUE (cpf_crianca, telefone_e164)",
        simples="A Maria repete, sem perceber, o telefone que já cadastrou. "
                "O sistema percebe e pede outro — dois contatos com o mesmo "
                "número seriam um contato só.",
    )
    api.responde(TEL_MARIA, "21988881234")
    api.responde(TEL_MARIA, "21 97777-5555")
    nota(
        tecnico="2o contato fecha a sessao e a fila destrava sozinha (secao 6.2)",
        simples="Com o segundo contato, a conversa da Ana termina — e note "
                "que o Bruno, que estava na fila, é chamado na sequência sem a "
                "família ter pedido nada.",
    )

    cabecalho(
        "CENARIO 4 - Captura do Bruno, iniciada pela fila",
        "4. A conversa do Bruno emenda na da Ana",
    )
    api.responde(TEL_MARIA, "Joana Souza")
    api.responde(TEL_MARIA, "avó")
    api.responde(TEL_MARIA, "+55 21 98888-1234")
    nota(
        tecnico="mesmo telefone da Ana e' aceito aqui: a arvore e' por crianca",
        simples="A Joana é a mesma avó, com o mesmo telefone que foi recusado "
                "há pouco. Aqui é aceito: cada criança tem a sua própria lista "
                "de contatos, e a avó pode ser contato dos dois netos.",
    )
    nota(
        tecnico="familia diz que nao quer o segundo contato",
        simples="A Maria decide não cadastrar um segundo contato para o Bruno.",
    )
    api.responde(TEL_MARIA, "não")

    cabecalho(
        "CENARIO 5 - Arvore de contato de cada crianca (GET /criancas/:cpf)",
        "5. O que ficou registrado",
    )
    nota(tecnico=f"GET /criancas/{CPF_ANA}")
    api.crianca(CPF_ANA)
    nota(tecnico=f"GET /criancas/{CPF_BRUNO}")
    api.crianca(CPF_BRUNO)

    cabecalho(
        "CENARIO 6 - Rejeicoes e no-ops",
        "6. O que o sistema recusa",
    )
    nota(
        tecnico="inscricao sem CPF (secao 8.3) -> 422, nada e' criado",
        simples="Inscrição sem o CPF da criança: recusada por inteiro, porque o "
                "CPF é o que identifica a criança no sistema.",
    )
    api.inscricao(
        codigo_inscricao="INSC-2026-000199",
        crianca_nome="Sem Cpf",
        responsavel_nome="Fulana",
        responsavel_telefone="+5521999990009",
    )
    nota(
        tecnico="CPF com digito verificador errado -> 422",
        simples="CPF com a quantidade certa de números, mas inválido "
                "(erro de digitação): também recusado.",
    )
    api.inscricao(
        codigo_inscricao="INSC-2026-000200",
        crianca_cpf="11122233399",
        crianca_nome="Dv Errado",
        responsavel_nome="Fulana",
        responsavel_telefone="+5521999990009",
    )
    nota(
        tecnico="codigo_inscricao ja usado por outra crianca -> 409",
        simples="Número de inscrição que já pertence a outra criança: recusado.",
    )
    api.inscricao(
        codigo_inscricao="INSC-2026-000123",
        crianca_cpf=gera_cpf_valido("111444777"),
        crianca_nome="Outra Crianca",
        responsavel_nome="Fulana",
        responsavel_telefone="+5521999990009",
    )
    nota(
        tecnico="reenvio da inscricao da Ana (ja tem 2 contatos) -> acao=NENHUMA",
        simples="A mesma inscrição da Ana chega de novo (acontece). O sistema "
                "não duplica nada e não incomoda a família outra vez.",
    )
    api.inscricao(
        codigo_inscricao="INSC-2026-000123",
        crianca_cpf=CPF_ANA,
        crianca_nome="Ana Silva",
        responsavel_nome="Maria Silva",
        responsavel_telefone=TEL_MARIA,
    )
    nota(
        tecnico="mensagem de numero nao cadastrado -> ignorada",
        simples="Alguém escreve de um número que não está cadastrado: ignorado.",
    )
    api.responde(TEL_DESCONHECIDO, "oi")
    nota(
        tecnico="mensagem sem sessao aberta -> ignorada",
        simples="A Maria manda um agradecimento solto, sem pergunta em aberto: "
                "o sistema não responde nada.",
    )
    api.responde(TEL_MARIA, "obrigada!")


def envelhece_sessao(
    caminho: Path, telefone: str, minutos: int, descricao: str
) -> None:
    """Recua o relogio de silencio da sessao ativa daquele responsavel.

    Simula horas de silencio em milissegundos - sem isto o cenario exigiria
    esperar de verdade. Mexe so em `ultima_resposta_em`, que e' exatamente o
    campo que a varredura le. E' manipulacao direta do banco feita pela demo,
    nao comportamento da aplicacao.
    """
    alvo = datetime.now(timezone.utc) - timedelta(minutes=minutos)
    marca = alvo.strftime("%Y-%m-%dT%H:%M:%S.") + f"{alvo.microsecond // 1000:03d}Z"
    con = sqlite3.connect(caminho)
    cursor = con.execute(
        "UPDATE conversa_captura SET ultima_resposta_em = ? WHERE status = 'EM_ANDAMENTO' "
        "AND id_responsavel = (SELECT id FROM responsavel WHERE telefone_e164 = ?)",
        (marca, telefone),
    )
    con.commit()
    if SIMPLES:
        sistema(f"({descricao})")
    else:
        print(f"   [demo] recuou ultima_resposta_em em {minutos} min "
              f"({cursor.rowcount} sessao/oes)")
    con.close()


def roda_expiracao(api: Api, caminho: Path) -> None:
    cabecalho(
        "CENARIO 7 - Familia para de responder e bloqueia o irmao (secao 8.4)",
        "7. E quando a família simplesmente para de responder?",
    )
    nota(
        tecnico="Carla inscreve Duda -> captura inicia",
        simples="Outra família: a Carla, mãe da Duda e do Elias. A inscrição da "
                "Duda chega e a conversa começa.",
    )
    api.inscricao(
        codigo_inscricao="INSC-2026-000301",
        crianca_cpf=CPF_DUDA,
        crianca_nome="Duda Nunes",
        responsavel_nome="Carla Nunes",
        responsavel_telefone=TEL_CARLA,
    )
    nota(
        tecnico="Carla inscreve Elias com a captura da Duda aberta -> Elias enfileirado",
        simples="O irmão Elias também é inscrito. Como a conversa da Duda "
                "está aberta, ele entra na fila e espera a vez.",
    )
    api.inscricao(
        codigo_inscricao="INSC-2026-000302",
        crianca_cpf=CPF_ELIAS,
        crianca_nome="Elias Nunes",
        responsavel_nome="Carla Nunes",
        responsavel_telefone=TEL_CARLA,
    )
    nota(
        tecnico="Carla responde o nome e para de responder",
        simples="A Carla responde o primeiro campo e... para. Vida real: "
                "distração, correria, celular sem bateria.",
    )
    api.responde(TEL_CARLA, "Tereza Nunes")
    nota(
        tecnico="ANTES DA CORRECAO: a sessao ficava aqui para sempre e o Elias, "
                "enfileirado, nunca receberia convite nenhum.",
        simples="Era exatamente aqui que estava o problema: a conversa ficava "
                "parada para sempre, e o Elias — esperando na fila atrás "
                "dela — nunca receberia convite nenhum. Inscrito, válido, "
                "e invisível.",
    )

    nota(
        tecnico="24h de silencio + POST /manutencao/varrer-sessoes -> lembrete",
        simples="Passa um dia. O sistema faz sua verificação periódica e manda "
                "um lembrete — retomando exatamente a pergunta onde parou, "
                "sem obrigar a família a começar de novo.",
    )
    envelhece_sessao(caminho, TEL_CARLA, 25 * 60, "passou 1 dia sem resposta")
    api.varrer()

    nota(
        tecnico="varredura de novo, sem novo silencio -> nada acontece (idempotente)",
        simples="A verificação roda de novo em seguida. Nada acontece — ela "
                "não manda lembrete repetido nem faz nada duas vezes.",
    )
    api.varrer()

    nota(
        tecnico="72h de silencio + varredura -> expira e destrava a fila",
        simples="Passam três dias no total e a Carla continua em silêncio. O "
                "sistema desiste dessa conversa — e a MESMA verificação que "
                "desiste da Duda já chama o Elias da fila.",
    )
    envelhece_sessao(caminho, TEL_CARLA, 73 * 60, "passaram 3 dias sem resposta")
    api.varrer()

    nota(
        tecnico="estado das duas criancas",
        simples="Veja o estado das duas crianças: a conversa da Duda foi "
                "encerrada sem contato nenhum, e a do Elias está aberta agora.",
    )
    api.crianca(CPF_DUDA)
    api.crianca(CPF_ELIAS)

    nota(
        tecnico="Carla agora responde pelo Elias e conclui com 1 contato",
        simples="Dessa vez a Carla responde e conclui o cadastro do Elias.",
    )
    api.responde(TEL_CARLA, "Marcia Nunes")
    api.responde(TEL_CARLA, "tia")
    api.responde(TEL_CARLA, "(21) 96666-7777")
    api.responde(TEL_CARLA, "nao")

    cabecalho(
        "CENARIO 8 - Mensagem tardia reabre a captura que expirou",
        "8. A família volta depois. E agora?",
    )
    nota(
        tecnico="Carla escreve do nada; a Duda ficou sem nenhum contato",
        simples="Dias depois a Carla escreve por conta própria. A Duda ficou "
                "sem contato nenhum, então o sistema retoma aquele cadastro "
                "abandonado em vez de ignorar a mensagem.",
    )
    api.responde(TEL_CARLA, "oi, ainda da tempo?")
    nota(
        tecnico="o texto NAO foi consumido como nome: 'oi, ainda da tempo?' nao "
                "pode virar um contato de apoio. A pergunta e' repetida.",
        simples="Detalhe importante: o 'oi, ainda dá tempo?' NÃO foi tratado "
                "como o nome da pessoa de confiança. O sistema repete a "
                "pergunta — melhor repetir do que registrar um contato "
                "chamado 'oi'.",
    )
    api.responde(TEL_CARLA, "Tereza Nunes")
    api.responde(TEL_CARLA, "avó")
    api.responde(TEL_CARLA, "21 95555-4444")
    api.responde(TEL_CARLA, "nao")
    nota(
        tecnico="arvore da Duda finalmente montada, depois de uma sessao expirada",
        simples="A Duda, que tinha sido abandonada no meio do caminho, termina "
                "com o contato de apoio registrado.",
    )
    api.crianca(CPF_DUDA)


def prova_trigger_no_banco(caminho: Path) -> None:
    """Decisao 3: o limite de 2 esta no banco, nao so na aplicacao."""
    cabecalho(
        "CENARIO 9 - Limite de 2 contatos travado no banco (decisao 3)",
        "9. O limite de 2 contatos é inviolável",
    )
    nota(
        tecnico="INSERT direto de um 3o contato de apoio para a Ana, sem passar pela app",
        simples="Última prova: tentamos gravar um terceiro contato para a Ana "
                "por fora do sistema, direto no banco de dados. Se a regra "
                "estivesse só no programa, isso passaria.",
    )
    con = sqlite3.connect(caminho)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        con.execute(
            "INSERT INTO contato_apoio (id, cpf_crianca, nome, grau_relacao, "
            "telefone_e164) VALUES ('x', ?, 'Terceiro', 'amigo', '+5521955550000')",
            (CPF_ANA,),
        )
        print("   FALHOU: o banco aceitou o 3o contato")
    except sqlite3.IntegrityError as erro:
        if SIMPLES:
            marca("✓", "Bloqueado pelo próprio banco de dados. A regra não "
                       "depende do programa estar correto.")
        else:
            print(f"   IntegrityError: {erro}")
            print("   -> trigger trg_max_contatos_apoio barrou "
                  "(equivale ao RAISE do plpgsql)")

    if not SIMPLES:
        nota(tecnico="SELECT no CPF do Bruno para confirmar que o zero a esquerda sobreviveu")
        linha = con.execute(
            "SELECT cpf, typeof(cpf) AS tipo, nome FROM crianca WHERE nome = 'Bruno Silva'"
        ).fetchone()
        print(f"   cpf={linha[0]!r}  typeof={linha[1]}  nome={linha[2]}")
    con.close()


def resumo_final(api: Api) -> None:
    if not SIMPLES:
        return
    cabecalho("", "Resumo: a árvore de contato de cada criança")
    for cpf in (CPF_ANA, CPF_BRUNO, CPF_DUDA, CPF_ELIAS):
        api.crianca(cpf)
    print("\n  Nenhuma dessas famílias precisou instalar aplicativo, criar senha "
          "ou\n  acessar site nenhum. Tudo foi respondido pelo WhatsApp, uma "
          "pergunta\n  por vez.")


# ------------------------------------------------------------------ execucao


def main() -> None:
    global SIMPLES, PAUSA, RITMO

    # O console do Windows usa cp1252 por padrao no Python 3.13, o que quebra
    # os acentos dos templates.
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except AttributeError:
        pass

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--simples", action="store_true",
                    help="saida limpa, como uma conversa de WhatsApp")
    ap.add_argument("--pausa", action="store_true",
                    help="espera Enter entre as mensagens")
    ap.add_argument("--devagar", nargs="?", type=float, const=1.0, default=0.0,
                    metavar="FATOR",
                    help="pausa proporcional ao texto, para gravar em video "
                         "(1.0 = ritmo de leitura; 0.5 = duas vezes mais rapido)")
    ap.add_argument("--parte",
                    choices=("essencial", "tudo", "captura", "expiracao"),
                    default="essencial",
                    help="essencial (padrao) = uma inscricao e a captura dos "
                         "contatos; tudo = os 9 cenarios; captura = cenarios "
                         "1 a 6; expiracao = cenarios 7 e 8")
    ap.add_argument("--base-url", help="bate num servidor ja rodando")
    ap.add_argument("--manter-banco", action="store_true",
                    help="nao apaga o banco da demo antes de rodar")
    args = ap.parse_args()

    SIMPLES = args.simples
    PAUSA = args.pausa
    RITMO = args.devagar

    if args.base_url:
        import httpx

        with httpx.Client(base_url=args.base_url, timeout=10) as cliente:
            api = Api(cliente)
            roda(api)
            resumo_final(api)
        print("\n(--base-url: cenarios 7 a 9 exigem acesso local ao arquivo do banco)")
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
        api = Api(cliente)
        if args.parte == "essencial":
            roda_essencial(api)
        else:
            # 'expiracao' pode rodar sozinho porque usa outra familia (Carla) e
            # nao depende do que os cenarios 1 a 6 deixaram no banco.
            if args.parte in ("tudo", "captura"):
                roda(api)
            if args.parte in ("tudo", "expiracao"):
                roda_expiracao(api, BANCO_DEMO)
            if args.parte in ("tudo", "captura"):
                prova_trigger_no_banco(BANCO_DEMO)
            if args.parte == "tudo":
                resumo_final(api)

    if not SIMPLES:
        print(f"\nBanco da demo: {BANCO_DEMO}")


if __name__ == "__main__":
    main()
