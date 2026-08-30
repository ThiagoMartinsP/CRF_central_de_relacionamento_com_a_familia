"""Templates de mensagem (secao 9 da especificacao).

Os placeholders usam a notacao [CHAVE] da propria especificacao, substituida
por replace literal - nao e' str.format, para que texto com chaves nao quebre.

Os quatro ultimos templates nao estao nomeados na tabela da secao 9: a spec
descreve o comportamento ("reenviar a pergunta com aviso de erro", "enviar
pergunta de nome (segundo contato)") sem batizar o template. Estao marcados
como acrescimo de implementacao.
"""

from __future__ import annotations

TEMPLATES: dict[str, str] = {
    "M1_BOAS_VINDAS_PEDE_CONTATO": (
        "Olá, [NOME]! Aqui é a Prefeitura do Rio – Educação. Recebemos a "
        "inscrição de [CRIANCA] para creche. Precisamos de 1 ou 2 pessoas de "
        "confiança para avisar caso não consigamos falar com você. Qual o nome "
        "da primeira pessoa?"
    ),
    "M1_PEDE_PARENTESCO": (
        "Qual o parentesco de [NOME_CONTATO] com você? (ex.: avó, tio, vizinho)"
    ),
    "M1_PEDE_TELEFONE": "Qual o telefone de [NOME_CONTATO]?",
    "M1_PERGUNTA_SEGUNDO": (
        "Contato registrado! Quer cadastrar mais uma pessoa para [CRIANCA]? "
        "Responda SIM ou NÃO."
    ),
    "M1_ENCERRAMENTO": (
        "Prontinho! Os contatos de apoio de [CRIANCA] estão registrados. Vamos "
        "avisar por aqui assim que surgir uma vaga."
    ),
    "M1_PEDE_CONTATO_PROXIMA_CRIANCA": (
        "Agora vamos cadastrar os contatos de apoio de [CRIANCA]. Qual o nome "
        "da primeira pessoa?"
    ),
    "ERRO_TELEFONE_INVALIDO": (
        "Não consegui entender esse número. Pode mandar de novo? "
        "(ex.: (21) 99999-0001)"
    ),
    # --- expiracao de sessao (secao 8.4) ---
    "M1_LEMBRETE_CAPTURA": (
        "Oi, [NOME]! Ainda estamos esperando os contatos de apoio de [CRIANCA]. "
        "[PERGUNTA]"
    ),
    "M1_EXPIRACAO_SEM_CONTATO": (
        "Não conseguimos concluir o cadastro dos contatos de apoio de [CRIANCA]. "
        "A inscrição continua valendo. Se quiser cadastrar agora, responda esta "
        "mensagem."
    ),
    "M1_EXPIRACAO_COM_CONTATO": (
        "Os contatos de apoio que você já cadastrou para [CRIANCA] estão "
        "registrados. Se quiser incluir outra pessoa, responda esta mensagem."
    ),
    "M1_REABERTURA_CAPTURA": (
        "Vamos retomar o cadastro dos contatos de apoio de [CRIANCA]. [PERGUNTA]"
    ),
    # --- acrescimos de implementacao (comportamento descrito, template sem nome) ---
    # Sem [CRIANCA] de proposito: estes dois sao usados embutidos em
    # M1_LEMBRETE_CAPTURA / M1_REABERTURA_CAPTURA, ou logo depois de uma
    # mensagem que ja nomeou a crianca. Repetir o nome soa robotico.
    "M1_PEDE_NOME_PRIMEIRO": "Qual o nome da primeira pessoa de confiança?",
    "M1_PEDE_NOME_SEGUNDO": "Qual o nome da segunda pessoa de confiança?",
    "ERRO_NOME_VAZIO": (
        "Preciso do nome da pessoa de confiança. Pode escrever o nome dela?"
    ),
    "ERRO_TELEFONE_DUPLICADO": (
        "Esse número já está cadastrado como contato de apoio de [CRIANCA]. "
        "Pode informar o telefone de outra pessoa?"
    ),
    "ERRO_LIMITE_CONTATOS": (
        "[CRIANCA] já tem 2 contatos de apoio cadastrados, que é o limite. "
        "Vamos avisar por aqui assim que surgir uma vaga."
    ),
}


def renderiza(template: str, **contexto: str) -> str:
    try:
        texto = TEMPLATES[template]
    except KeyError:
        raise ValueError(f"template desconhecido: {template}") from None
    for chave, valor in contexto.items():
        texto = texto.replace(f"[{chave.upper()}]", str(valor))
    return texto