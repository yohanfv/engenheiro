# -*- coding: utf-8 -*-
"""Idioma do engenheiro (português ou inglês). Tudo o que ele fala e mostra passa por aqui."""

IDIOMA = "pt"


def definir(lang):
    global IDIOMA
    IDIOMA = "en" if str(lang).lower().startswith("en") else "pt"


def en():
    return IDIOMA == "en"


def L(pt, ingles):
    """Escolhe o texto do idioma atual."""
    return ingles if IDIOMA == "en" else pt


def _pick(v):
    if isinstance(v, tuple) and len(v) == 2:
        return v[1] if IDIOMA == "en" else v[0]
    return v


class Bi(dict):
    """Dicionário cujos valores são (português, inglês): devolve o do idioma atual."""

    def __getitem__(self, k):
        return _pick(dict.__getitem__(self, k))

    def get(self, k, padrao=None):
        return _pick(dict.__getitem__(self, k)) if k in self else padrao

    def values(self):
        return [_pick(v) for v in dict.values(self)]

    def items(self):
        return [(k, _pick(v)) for k, v in dict.items(self)]


class BiLista(list):
    """Lista de (português, inglês)."""

    def __getitem__(self, i):
        v = list.__getitem__(self, i)
        return [_pick(x) for x in v] if isinstance(i, slice) else _pick(v)

    def __iter__(self):
        return (_pick(v) for v in list.__iter__(self))
