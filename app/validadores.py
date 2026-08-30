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

# Os canonicos sao grafados corretamente, com acento: este valor vai para o
# banco e e' exibido de volta a operadores e familias - "avo" no lugar de "avó"
# parece erro de digitacao do sistema.
_SINONIMOS_GRAU = {
    "mãe": ("mãe", "mamãe", "genitora"),
    "pai": ("pai", "papai", "genitor"),
    "avó": ("avó", "vovó"),
    "avô": ("avô", "vovô"),
    "tio": ("tio",),
    "tia": ("tia",),
    "irmão": ("irmão", "mano"),
    "irmã": ("irmã", "mana"),
    "vizinho": ("vizinho",),
    "vizinha": ("vizinha",),
    "amigo": ("amigo",),
    "amiga": ("amiga",),
    "madrinha": ("madrinha",),
    "padrinho": ("padrinho",),
    "primo": ("primo",),
    "prima": ("prima",),
}

_SEM_ACENTO_GRAU: dict[str, set[str]] = {}
for _canonico, _variantes in _SINONIMOS_GRAU.items():
    for _variante in _variantes:
        _SEM_ACENTO_GRAU.setdefault(_sem_acento(_variante), set()).add(_canonico)


def normaliza_grau_relacao(texto: str) -> str:
    """Casa contra a lista conhecida; se nao reconhecer, devolve o texto original.

    O campo e' TEXT no banco de proposito: uma resposta fora da lista nao pode
    travar a conversa.

    A familia digita sem acento com frequencia, entao ha um segundo passe sem
    acentuacao - mas ele so vale quando o resultado e' unico. "vovo" continua
    gravado como veio, porque pode ser avo ou avo (avó/avô) e chutar o genero
    de uma pessoa da rede de apoio e' pior do que guardar o texto cru.
    """
    limpo = (texto or "").strip()
    baixo = limpo.lower()
    for canonico, variantes in _SINONIMOS_GRAU.items():
        if baixo in variantes:
            return canonico
    candidatos = _SEM_ACENTO_GRAU.get(_sem_acento(baixo), set())
    if len(candidatos) == 1:
        return next(iter(candidatos))
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
