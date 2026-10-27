# -*- coding: utf-8 -*-
"""
Análise automática no fim de um treino (ou de qualquer sessão): ritmo contra a IA, setor mais fraco,
desgaste por composto, onde cada pneu esquenta, ajuste de acerto e plano de paradas para a corrida.
Lê os arquivos gravados na pasta da sessão, então também dá para rodar depois:  py analise.py <pasta>
"""

import csv
import json
import os
import statistics
import sys

import estrategia as est
from idioma import L as tr, en

RODAS = [("TE", ("traseiro esquerdo", "rear left")), ("TD", ("traseiro direito", "rear right")),
         ("DE", ("dianteiro esquerdo", "front left")), ("DD", ("dianteiro direito", "front right"))]
# nome gravado no voltas.csv (em português ou inglês, conforme o idioma da sessão) -> composto
COMP_ID = {"macio": est.MACIO, "médio": est.MEDIO, "duro": est.DURO,
           "soft": est.MACIO, "medium": est.MEDIO, "hard": est.DURO}


def _ler_csv(caminho):
    try:
        with open(caminho, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f, delimiter=";"))
    except OSError:
        return []


def _f(v, padrao=0.0):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return padrao


def _tempo(ms):
    ms = int(ms)
    m, r = divmod(ms, 60000)
    return f"{m}:{r / 1000:06.3f}" if m else f"{r / 1000:.3f}"


def _curvas(pista, comprimento):
    oficiais = est.dados_pista(pista).get("curvas") or []
    return [(rot, frac * comprimento) for rot, frac in oficiais] if comprimento else []


def _curva_mais_perto(dist, curvas):
    if not curvas:
        return None
    return min(curvas, key=lambda c: abs(c[1] - dist))[0]


def analisar(pasta, pista, comprimento=0, pct_corrida=50, nome_piloto="", nome_pista=""):
    """Devolve {"texto": relatório completo, "falado": resumo curto, "taxas": {composto_id: %/volta}}."""
    voltas = _ler_csv(os.path.join(pasta, "voltas.csv"))
    # a mesma volta gravada duas vezes (flashback, versões antigas): fica a que mediu a volta inteira
    por_volta = {}
    for v in voltas:
        k = v.get("volta")
        if k not in por_volta or _f(v.get("consumo_volta_kg")) > _f(por_volta[k].get("consumo_volta_kg")):
            por_volta[k] = v
    voltas = list(por_volta.values())
    todos = _ler_csv(os.path.join(pasta, "voltas_todos.csv"))
    linhas, falado = [], []
    nome_pista = nome_pista or est.dados_pista(pista).get("nome", "")

    limpas = [v for v in voltas if v.get("valida") == "1" and v.get("teve_pit") == "0" and _f(v.get("tempo_ms")) > 0]
    if not limpas:
        return {"texto": tr("Sem voltas limpas suficientes para analisar.", "Not enough clean laps to analyse."),
                "falado": "", "taxas": {}}

    # ---------- ritmo contra a IA ----------
    minha = min(limpas, key=lambda v: _f(v["tempo_ms"]))
    eu_nome = (nome_piloto or "").strip().lower()
    outros = [t for t in todos if t.get("valida") == "1" and t.get("teve_pit") == "0" and _f(t.get("tempo_ms")) > 0
              and (t.get("piloto", "").strip().lower() != eu_nome if eu_nome else True)]
    if eu_nome == "":
        outros = [t for t in outros if t.get("tempo_ms") != minha["tempo_ms"] or t.get("volta") != minha["volta"]]
    linhas.append(tr("RITMO", "PACE"))
    linhas.append(tr(f"  Sua melhor volta: {_tempo(_f(minha['tempo_ms']))} (volta {minha['volta']}, {minha['pneu']})",
                     f"  Your best lap: {_tempo(_f(minha['tempo_ms']))} (lap {minha['volta']}, {minha['pneu']})"))
    melhor_ia = min(outros, key=lambda t: _f(t["tempo_ms"])) if outros else None
    if melhor_ia:
        dif = (_f(minha["tempo_ms"]) - _f(melhor_ia["tempo_ms"])) / 1000
        ia_txt = f"{_tempo(_f(melhor_ia['tempo_ms']))} ({melhor_ia['piloto']}, {melhor_ia['pneu']})"
        linhas.append(tr(f"  Melhor da IA: {ia_txt}  -> você está {abs(dif):.3f} s {'atrás' if dif > 0 else 'à frente'}",
                         f"  Best AI lap: {ia_txt}  -> you are {abs(dif):.3f} s {'behind' if dif > 0 else 'ahead'}"))
        if dif > 0:
            falado.append(tr(f"Seu ritmo de uma volta está {est_dif(dif)} atrás da melhor volta da IA.",
                             f"Your one-lap pace is {est_dif(dif)} off the best AI lap."))
        else:
            falado.append(tr(f"Seu ritmo de uma volta está {est_dif(dif)} à frente da IA.",
                             f"Your one-lap pace is {est_dif(dif)} ahead of the AI."))
    # setores
    meus = [min(_f(v[k]) for v in limpas if _f(v[k]) > 0) for k in ("s1_ms", "s2_ms", "s3_ms")]
    if outros:
        ia = [min(_f(t[k]) for t in outros if _f(t[k]) > 0) for k in ("s1_ms", "s2_ms", "s3_ms")]
        difs = [(m - i) / 1000 for m, i in zip(meus, ia)]
        linhas.append(tr("  Setores (seu melhor x melhor da IA): ", "  Sectors (your best vs best AI): ") + "  ".join(
            f"S{k + 1} {'+' if d > 0 else ''}{d:.3f}" for k, d in enumerate(difs)))
        pior = max(range(3), key=lambda k: difs[k])
        if difs[pior] > 0.05:
            falado.append(tr(f"Onde mais dá para ganhar é o setor {pior + 1}.",
                             f"The most time to gain is in sector {pior + 1}."))
    tempos = [_f(v["tempo_ms"]) / 1000 for v in limpas]
    if len(tempos) >= 3:
        linhas.append(tr("  Média das voltas limpas: ", "  Average of clean laps: ")
                      + f"{_tempo(statistics.mean(tempos) * 1000)}  "
                      + tr("(desvio", "(std dev") + f" {statistics.pstdev(tempos):.3f} s)")

    # ---------- desgaste por composto ----------
    linhas.append("")
    linhas.append(tr("PNEUS", "TYRES"))
    taxas, consumo = {}, []
    for cid in est.SECOS:
        d = [_f(v["desgaste_na_volta"]) for v in limpas
             if COMP_ID.get(v.get("pneu")) == cid and 0 < _f(v["desgaste_na_volta"]) < 20]
        if len(d) >= 2:
            taxas[cid] = statistics.mean(d)
            linhas.append(tr(f"  {est.NOME[cid]}: {taxas[cid]:.2f}% por volta ({len(d)} voltas)",
                             f"  {est.NOME[cid]}: {taxas[cid]:.2f}% per lap ({len(d)} laps)"))
    consumo = [_f(v["consumo_volta_kg"]) for v in limpas if 0.3 < _f(v.get("consumo_volta_kg")) < 4]
    if consumo:
        linhas.append(tr(f"  Combustível: {statistics.mean(consumo):.2f} kg por volta",
                         f"  Fuel: {statistics.mean(consumo):.2f} kg per lap"))

    # ---------- temperatura: qual pneu e em qual curva ----------
    tele = _ler_csv(os.path.join(pasta, "telemetria.csv"))
    curvas = _curvas(pista, comprimento)
    quentes = {}
    for r in tele:
        if r.get("pit_status") not in ("0", "", None):
            continue
        dist = _f(r.get("dist_volta_m"), -1)
        if dist < 0:
            continue
        for col, nomes in RODAS:
            nome = nomes[1] if en() else nomes[0]
            t = _f(r.get(f"temp_sup_{col}"))
            if t >= 115:
                curva = _curva_mais_perto(dist, curvas) or f"{int(dist // 100) * 100} m"
                dianteiro = col.startswith("D")
                quentes.setdefault(nome, {}).setdefault(curva, []).append(t)
    sugestoes = []
    if quentes:
        linhas.append(tr("  Pontos de superaquecimento (superfície acima de 115°C):",
                         "  Overheating points (surface above 115°C):"))
        ranking = sorted(quentes.items(), key=lambda kv: -sum(len(v) for v in kv[1].values()))
        for nome, por_curva in ranking[:2]:
            top = sorted(por_curva.items(), key=lambda kv: -len(kv[1]))[:2]
            linhas.append(f"    {nome}: " + ", ".join(tr(f"curva {c} (até {max(v):.0f}°C)",
                                                          f"turn {c} (up to {max(v):.0f}°C)") for c, v in top))
        nome, por_curva = ranking[0]
        curva = sorted(por_curva.items(), key=lambda kv: -len(kv[1]))[0][0]
        falado.append(tr(f"O pneu que mais sofre é o {nome}, na curva {curva}.",
                         f"The tyre suffering most is the {nome}, in turn {curva}."))
        if "dianteiro" in nome or "front" in nome:
            sugestoes.append(tr(f"Barra estabilizadora dianteira 1 a 2 pontos mais macia e pressão do {nome} 0,3 mais baixa.",
                                f"Front anti-roll bar 1 to 2 clicks softer and {nome} pressure 0.3 lower."))
            sugestoes.append(tr(f"Na curva {curva}, espere o carro apontar antes de acelerar tudo.",
                                f"In turn {curva}, wait for the car to point before going full throttle."))
        else:
            sugestoes.append(tr("Diferencial na aceleração 5 pontos mais baixo e acelerador mais progressivo na saída das curvas lentas.",
                                "On-throttle differential 5 points lower and smoother throttle out of the slow corners."))

    # ---------- acerto usado ----------
    try:
        with open(os.path.join(pasta, "sessao.json"), encoding="utf-8") as f:
            sj = json.load(f)
        ac = (sj.get("acertos") or [{}])[-1].get("acerto") or {}
    except (OSError, ValueError):
        ac = {}
    if sugestoes:
        linhas.append("")
        linhas.append(tr("SUGESTÃO DE ACERTO", "SETUP SUGGESTION"))
        if ac:
            asas = f"{ac.get('frontWing', 0):.0f}/{ac.get('rearWing', 0):.0f}"
            barras = f"{ac.get('frontAntiRollBar', 0):.0f}/{ac.get('rearAntiRollBar', 0):.0f}"
            dif_ = f"{ac.get('onThrottle', 0):.0f}"
            linhas.append(tr(f"  (acerto usado: asas {asas}, barras {barras}, diferencial {dif_}%)",
                             f"  (setup used: wings {asas}, anti-roll bars {barras}, differential {dif_}%)"))
        for s in sugestoes:
            linhas.append(f"  - {s}")

    # ---------- plano para a corrida ----------
    n = est.voltas_corrida(pista, pct_corrida)
    if n and taxas:
        corrida = {c: t * est.FATOR_TANQUE_CHEIO for c, t in est.taxas_estimadas(
            next(iter(taxas)), taxas[next(iter(taxas))], historico={str(k): v for k, v in taxas.items()}).items()}
        melhores = []
        for inicio in est.SECOS:
            jogos = [(c, 0.0) for c in est.SECOS if c != inicio] + [(inicio, 0.0)]
            planos = est.planejar(n, inicio, 0.0, corrida, jogos, est.perda_box(pista), total=n)
            for p in est.melhores_por_paradas(planos).values():
                melhores.append((p["tempo"], inicio, p))
        if melhores:
            melhores.sort(key=lambda x: x[0])
            linhas.append("")
            linhas.append(tr(f"PLANO PARA A CORRIDA ({n} voltas, {pct_corrida}%)",
                             f"RACE PLAN ({n} laps, {pct_corrida}%)"))
            vistos = set()
            for tempo, inicio, p in melhores:
                chave = (inicio, len(p["paradas"]))
                if chave in vistos or len(vistos) >= 5:
                    continue
                vistos.add(chave)
                desc = est.descrever(p, 1, n)
                fim = ", ".join(f"{x:.0f}%" for x in p["desg_fim"])
                linhas.append(tr(f"  Largando de {est.NOME[inicio]}: {desc} (desgaste no fim de cada stint: {fim};",
                                 f"  Starting on {est.NOME[inicio]}: {desc} (wear at the end of each stint: {fim};")
                              + f" {tempo - melhores[0][0]:+.1f} s)")
            _, inicio, p = melhores[0]
            falado.append(tr(f"Para a corrida: largar de {est.NOME[inicio]}. {est.descrever(p, 1, n)}",
                             f"For the race: start on the {est.NOME[inicio]}. {est.descrever(p, 1, n)}"))
    texto = (tr("ANÁLISE DA SESSÃO", "SESSION ANALYSIS") + f" — {nome_pista}\n" + "=" * 60 + "\n"
             + "\n".join(linhas) + "\n")
    return {"texto": texto, "falado": " ".join(falado), "taxas": taxas}


def est_dif(seg):
    try:
        import falas
        return falas.dif(seg)
    except Exception:  # noqa: BLE001
        return f"{abs(seg):.1f} s"


if __name__ == "__main__":
    pasta = sys.argv[1]
    with open(os.path.join(pasta, "sessao.json"), encoding="utf-8") as f:
        pid = json.load(f).get("pista_id", -1)
    r = analisar(pasta, pid, float(sys.argv[2]) if len(sys.argv) > 2 else 0)
    print(r["texto"])
    print("FALADO:", r["falado"])
