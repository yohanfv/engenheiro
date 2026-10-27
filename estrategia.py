# -*- coding: utf-8 -*-
"""
Calculadora de estratégia: compara zero, uma e duas paradas com o desgaste real dos seus pneus,
os jogos de pneus que você ainda tem e o tempo perdido no box em cada pista.

Modelo (simples e transparente):
  tempo de uma volta = diferença do composto + perda por desgaste (0,018 s por ponto de desgaste)
  cada parada custa o tempo de box da pista (menos com Safety Car)
  nenhum pneu passa do limite de desgaste (padrão 72%, perto do máximo que o jogo aceita)
"""

import json
import math
import os
import sys

AQUI = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))

MACIO, MEDIO, DURO, INTER, CHUVA = 16, 17, 18, 7, 8
SECOS = (MACIO, MEDIO, DURO)
from idioma import Bi, L as tr  # noqa: E402

NOME = Bi({MACIO: ("macio", "soft"), MEDIO: ("médio", "medium"), DURO: ("duro", "hard"),
           INTER: ("intermediário", "intermediate"), CHUVA: ("de chuva", "full wet")})

# desgaste relativo ao médio e diferença de ritmo (s/volta) com pneu novo, quando o jogo não informa
RAZAO_DESGASTE = {MACIO: 1.45, MEDIO: 1.0, DURO: 0.72}
DELTA_RITMO = {MACIO: -0.45, MEDIO: 0.0, DURO: 0.40}
PERDA_POR_PONTO = 0.018      # s por volta a cada 1% de desgaste
LIMITE_PADRAO = 75.0
# o pneu gasta menos conforme o tanque esvazia: fator ao longo da corrida (1,15 na largada, 0,80 no fim).
# Calibrado na Áustria: médio 5,6%/volta no início, 4,8% no meio; duro 4,0% no fim.


def fator_tanque(x):
    """x = fração da corrida (0 = largada, 1 = bandeirada)."""
    return 1.15 - 0.35 * max(0.0, min(1.0, x))
FATOR_TANQUE_CHEIO = 1.25    # na corrida o carro pesado gasta mais pneu que no treino (Áustria: 4,3 -> 5,6%)

# voltas oficiais de cada GP (id da pista no jogo)
VOLTAS_OFICIAIS = {0: 58, 2: 56, 3: 57, 4: 66, 5: 78, 6: 70, 7: 52, 9: 70, 10: 44, 11: 53, 12: 62, 13: 53,
                   14: 58, 15: 56, 16: 71, 17: 71, 19: 71, 20: 51, 26: 72, 27: 63, 29: 50, 30: 57, 31: 50, 32: 57}

_PISTAS = None


def dados_pista(pista):
    global _PISTAS
    if _PISTAS is None:
        try:
            with open(os.path.join(AQUI, "mapas", "curvas.json"), encoding="utf-8") as f:
                _PISTAS = {int(k): v for k, v in json.load(f).items()}
        except (OSError, ValueError):
            _PISTAS = {}
    return _PISTAS.get(pista, {})


def perda_box(pista, sc=0):
    """Tempo perdido numa parada. No jogo o box é um pouco mais rápido que na vida real (~85%)."""
    d = dados_pista(pista)
    real = d.get("perda_box_sc" if sc == 1 else ("perda_box_vsc" if sc == 2 else "perda_box")) or (
        13.5 if sc == 1 else 14.5 if sc == 2 else 21.5)
    return real * 0.85


def voltas_corrida(pista, pct=50):
    oficial = VOLTAS_OFICIAIS.get(pista)
    return math.ceil(oficial * pct / 100) if oficial else 0


def _stint(n, comp, w0, taxa, deltas):
    """Tempo extra (s) de n voltas com um jogo que começa com w0% de desgaste (taxa média do stint)."""
    return n * deltas.get(comp, 0.0) + PERDA_POR_PONTO * (n * w0 + taxa * n * n / 2)


def planejar(restantes, comp_atual, desg_atual, taxas, conjuntos, perda, compostos_usados=(),
             limite=LIMITE_PADRAO, deltas=None, max_paradas=2, chuva=False, total=None):
    """
    restantes: voltas que faltam (incluindo a atual)
    taxas: {composto: % de desgaste por volta}
    conjuntos: [(composto, desgaste_inicial), ...] jogos disponíveis para trocar
    Devolve a lista de planos, do mais rápido ao mais lento:
      {"paradas": [(voltas_a_partir_de_agora, composto), ...], "tempo": s, "desg_fim": [...]}
    """
    deltas = dict(DELTA_RITMO, **(deltas or {}))
    if not taxas.get(comp_atual) or restantes <= 0:
        return []
    total = max(total or restantes, restantes)
    feitas = total - restantes                     # voltas já completadas
    f_agora = fator_tanque((feitas + 0.5) / total)
    base = {c: t / f_agora for c, t in taxas.items() if t}

    def taxa(comp, ini, n):
        """% por volta médio de um stint que começa daqui a 'ini' voltas e dura n voltas."""
        return base[comp] * fator_tanque((feitas + ini + n / 2) / total)


    jogos = sorted(conjuntos, key=lambda c: c[1])
    planos = []

    def regra_ok(comps):
        if chuva:
            return True
        secos = {c for c in comps if c in SECOS}
        return len(secos) >= 2

    def cabe(comp, w0, n, ini=0):
        return comp in base and w0 + taxa(comp, ini, n) * n <= limite

    usados = set(compostos_usados) | {comp_atual}
    # sem parar
    if cabe(comp_atual, desg_atual, restantes) and regra_ok(usados):
        ta = taxa(comp_atual, 0, restantes)
        planos.append({"paradas": [], "tempo": _stint(restantes, comp_atual, desg_atual, ta, deltas),
                       "desg_fim": [desg_atual + ta * restantes]})
    if max_paradas >= 1:
        for s in range(1, restantes):
            if not cabe(comp_atual, desg_atual, s):
                break
            ta = taxa(comp_atual, 0, s)
            t0 = _stint(s, comp_atual, desg_atual, ta, deltas)
            vistos = set()
            for i, (c1, w1) in enumerate(jogos):
                if (c1, w1) in vistos:
                    continue
                vistos.add((c1, w1))
                n1 = restantes - s
                if cabe(c1, w1, n1, s) and regra_ok(usados | {c1}):
                    t1 = taxa(c1, s, n1)
                    planos.append({"paradas": [(s, c1)], "tempo": t0 + perda + _stint(n1, c1, w1, t1, deltas),
                                   "desg_fim": [desg_atual + ta * s, w1 + t1 * n1]})
                if max_paradas >= 2:
                    for s2 in range(s + 1, restantes):
                        n_meio = s2 - s
                        if not cabe(c1, w1, n_meio, s):
                            break
                        tm = taxa(c1, s, n_meio)
                        meio = _stint(n_meio, c1, w1, tm, deltas)
                        vistos2 = set()
                        for j, (c2, w2) in enumerate(jogos):
                            if j == i or (c2, w2) in vistos2:
                                continue
                            vistos2.add((c2, w2))
                            n2 = restantes - s2
                            if cabe(c2, w2, n2, s2) and regra_ok(usados | {c1, c2}):
                                t2 = taxa(c2, s2, n2)
                                planos.append({"paradas": [(s, c1), (s2, c2)],
                                               "tempo": t0 + 2 * perda + meio + _stint(n2, c2, w2, t2, deltas),
                                               "desg_fim": [desg_atual + ta * s, w1 + tm * n_meio, w2 + t2 * n2]})
    planos.sort(key=lambda p: p["tempo"])
    return planos


def melhores_por_paradas(planos):
    """O melhor plano de cada quantidade de paradas: {0: plano, 1: plano, 2: plano}."""
    out = {}
    for p in planos:
        k = len(p["paradas"])
        if k not in out:
            out[k] = p
    return out


def taxas_estimadas(comp_medido, taxa_medida, vida_util=None, historico=None, fator=1.0):
    """Desgaste por volta de cada composto seco.
    Usa, em ordem: o medido agora; o histórico do fim de semana (ajustado pelo fator); a vida útil que o
    jogo informa para cada composto; e por fim as proporções padrão."""
    taxas = {}
    historico = historico or {}
    vida_util = vida_util or {}
    if comp_medido in SECOS and taxa_medida:
        taxas[comp_medido] = taxa_medida
    ref_comp, ref_taxa = (comp_medido, taxa_medida) if taxa_medida else (None, None)
    if ref_taxa is None:
        for c in SECOS:
            if historico.get(str(c)) or historico.get(c):
                ref_comp, ref_taxa = c, (historico.get(str(c)) or historico.get(c)) * fator
                break
    for c in SECOS:
        if c in taxas:
            continue
        h = historico.get(str(c)) or historico.get(c)
        if h:
            # ajusta o histórico do treino pela diferença vista hoje no composto medido
            ajuste = fator
            hm = historico.get(str(comp_medido)) or historico.get(comp_medido)
            if taxa_medida and hm:
                ajuste = taxa_medida / hm
            taxas[c] = h * ajuste
        elif ref_taxa:
            if vida_util.get(c) and vida_util.get(ref_comp):
                taxas[c] = ref_taxa * vida_util[ref_comp] / vida_util[c]
            else:
                taxas[c] = ref_taxa * RAZAO_DESGASTE[c] / RAZAO_DESGASTE.get(ref_comp, 1.0)
    return taxas


def descrever(plano, volta_atual, restantes):
    """Texto curto do plano para o rádio. volta_atual = volta em andamento."""
    if not plano["paradas"]:
        return tr(f"Sem parar: o pneu chega ao fim com cerca de {plano['desg_fim'][0]:.0f} por cento.",
                  f"No stop: the tyres reach the end at about {plano['desg_fim'][0]:.0f} percent.")
    partes = [tr(f"na volta {volta_atual + v - 1} para o {NOME.get(comp, 'pneu')}",
                 f"on lap {volta_atual + v - 1} for the {NOME.get(comp, 'tyre')}") for v, comp in plano["paradas"]]
    if len(partes) == 1:
        return tr(f"Uma parada, {partes[0]}.", f"One stop, {partes[0]}.")
    return tr(f"Duas paradas: {partes[0]} e {partes[1]}.", f"Two stops: {partes[0]} and {partes[1]}.")
