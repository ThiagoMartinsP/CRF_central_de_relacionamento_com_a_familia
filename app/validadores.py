"""Validacao e normalizacao de entrada (secao 7 da especificacao)."""

from __future__ import annotations

import re
import unicodedata

_NAO_DIGITO = re.compile(r"\D+")


def so_digitos(bruto: object) -> str:
    return _NAO_DIGITO.sub("", str(bruto or ""))


def _sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# ---------------------------------------------------------------- CPF


def normaliza_cpf(bruto: object) -> str | None:
    """Retorna 11 digitos como string, ou None se o formato nao fechar.

    O `zfill` cobre o caso classico de o CPF ter chegado como numero no JSON
    (ex.: 01234567890 -> 1234567890), que apagaria o zero a esquerda.
    """
    if bruto is None:
        return None
    if isinstance(bruto, int):
        digitos = str(bruto).zfill(11)
    else:
        digitos = so_digitos(bruto)
    return digitos if len(digitos) == 11 else None


def cpf_dv_valido(cpf: str) -> bool:
    """Digito verificador oficial da Receita. Roda na aplicacao, nao no banco."""
    if len(cpf) != 11 or not cpf.isdigit() or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        resto = (soma * 10) % 11
        digito = 0 if resto == 10 else resto
        if digito != int(cpf[tamanho]):
            return False
    return True


def gera_cpf_valido(base9: str) -> str:
    """Completa 9 digitos com os 2 DVs corretos. Para dado sintetico de demo."""
    cpf = so_digitos(base9).zfill(9)[:9]
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        resto = (soma * 10) % 11
        cpf += "0" if resto == 10 else str(resto)
    return cpf


# ---------------------------------------------------------------- TELEFONE


def normaliza_e164_brasil(bruto: object) -> str | None:
    """Aceita '(21) 99999-0001', '21999990001', '+5521999990001'.

    Normaliza para +55DDD9XXXXXXXX. Numero fixo e' rejeitado: o canal do MVP
    e' WhatsApp, logo precisa ser movel.
    """
    digitos = so_digitos(bruto).lstrip("0")
    if len(digitos) in (12, 13) and digitos.startswith("55"):
        digitos = digitos[2:]

    if len(digitos) == 11:
        ddd, numero = digitos[:2], digitos[2:]
        if numero[0] != "9":
            return None
    elif len(digitos) == 10:
        ddd, numero = digitos[:2], digitos[2:]
        if numero[0] not in "6789":  # 2-5 = fixo
            return None
        numero = "9" + numero  # celular no formato antigo, de 8 digitos
    else:
        return None

    if not 11 <= int(ddd) <= 99:
        return None
    return f"+55{ddd}{numero}"


# ---------------------------------------------------------------- PARENTESCO

_SINONIMOS_GRAU = {
    "mae": ("mae", "mamae", "genitora"),
    "pai": ("pai", "papai", "genitor"),
    "avo": ("avo", "vovo", "vovoo"),
    "tio": ("tio",),
    "tia": ("tia",),
    "irmao": ("irmao", "mano"),
    "irma": ("irma", "mana"),
    "vizinho": ("vizinho", "vizinha"),
    "amigo": ("amigo", "amiga"),
    "madrinha": ("madrinha",),
    "padrinho": ("padrinho",),
    "primo": ("primo", "prima"),
}


def normaliza_grau_relacao(texto: str) -> str:
    """Casa contra a lista conhecida; se nao reconhecer, devolve o texto original.

    O campo e' TEXT no banco de proposito: uma resposta fora da lista nao pode
    travar a conversa.
    """
    limpo = (texto or "").strip()
    chave = _sem_acento(limpo).lower()
    for canonico, variantes in _SINONIMOS_GRAU.items():
        if chave in variantes:
            return canonico
    return limpo


# ---------------------------------------------------------------- SIM / NAO

_SIM = {"sim", "s", "quero", "claro", "pode", "ok", "positivo", "1", "yes"}
_NAO = {"nao", "n", "negativo", "0", "no", "chega", "so isso", "nao quero"}


def normaliza_sim_nao(texto: str) -> str | None:
    chave = _sem_acento((texto or "").strip()).lower().rstrip(".!")
    if chave in _SIM:
        return "SIM"
    if chave in _NAO:
        return "NAO"
    return None
