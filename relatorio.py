# -*- coding: utf-8 -*-
"""
Relatório pós-sessão (relatorio.html): compara a sua melhor volta com as outras, curva por curva.

Para cada zona de freada da melhor volta mede: ponto de freada, velocidade mínima e tempo gasto
no trecho. Depois compara com as outras voltas válidas e aponta onde está o tempo.
"""

import bisect
import json
import os
import statistics
from datetime import datetime

import idioma
from idioma import L as tr

PASSO_M = 6.0          # resolução das séries no gráfico (metros)


def _raiz():
    import sys
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))


def _serie(amostras):
    """Amostras ordenadas por distância, sem repetições/voltas para trás."""
    out, ult = [], -1.0
    for a in sorted(amostras, key=lambda x: x[0]):
        if a[0] > ult:
            out.append(a)
            ult = a[0]
    return out


def _interp(ds, vs, d):
    k = bisect.bisect_left(ds, d)
    if k <= 0:
        return vs[0]
    if k >= len(ds):
        return vs[-1]
    f = (d - ds[k - 1]) / max(1e-6, ds[k] - ds[k - 1])
    return vs[k - 1] + f * (vs[k] - vs[k - 1])


def _curvas(s):
    """Zonas de freada da volta: início da freada, ápice (vel. mínima) e retomada do acelerador."""
    curvas = []
    i, n = 0, len(s)
    while i < n:
        d, _, vel, acel, freio = s[i][:5]
        if freio >= 0.2 and (not curvas or d - curvas[-1]["saida"] > 60):
            ini = d
            j = i
            vmin, apice = vel, i
            while j < n and s[j][0] - ini < 600:
                if s[j][2] < vmin:
                    vmin, apice = s[j][2], j
                if j > apice and s[j][3] >= 0.9 and s[j][4] < 0.05:
                    break
                j += 1
            saida = s[min(j, n - 1)][0]
            curvas.append({"freada": round(ini, 1), "apice": round(s[apice][0], 1), "saida": round(saida, 1),
                           "vmin": vmin, "x": s[apice][6], "z": s[apice][7]})
            i = j
        i += 1
    return curvas


def _analisar(melhor, outras):
    sm = _serie(melhor["amostras"])
    dm, tm = [a[0] for a in sm], [a[1] for a in sm]
    curvas = _curvas(sm)
    for k, c in enumerate(curvas):
        c["n"] = k + 1
        ini, fim = c["freada"] - 50, c["saida"] + 50
        t_melhor = _interp(dm, tm, fim) - _interp(dm, tm, ini)
        perdas, freadas, vmins = [], [], []
        for v in outras:
            so = _serie(v["amostras"])
            if len(so) < 50:
                continue
            do, to = [a[0] for a in so], [a[1] for a in so]
            perdas.append((_interp(do, to, fim) - _interp(do, to, ini)) - t_melhor)
            zona = [a for a in so if c["freada"] - 120 <= a[0] <= c["saida"]]
            f = next((a[0] for a in zona if a[4] >= 0.2), None)
            if f is not None:
                freadas.append(f - c["freada"])
            if zona:
                vmins.append(min(a[2] for a in zona) - c["vmin"])
        c["perda_ms"] = round(statistics.mean(perdas)) if perdas else 0
        c["freada_dif_m"] = round(statistics.mean(freadas), 1) if freadas else 0
        c["vmin_dif"] = round(statistics.mean(vmins), 1) if vmins else 0
    return curvas


def _dicas(curvas):
    dicas = []
    for c in sorted(curvas, key=lambda x: -x["perda_ms"])[:3]:
        if c["perda_ms"] < 40:
            continue
        perda = f"{c['perda_ms'] / 1000:.2f}"
        txt = tr(f"Curva {c['n']} (freada aos {c['freada']:.0f} m): você perde em média {perda} s em relação à sua melhor volta.",
                 f"Corner {c['n']} (braking at {c['freada']:.0f} m): you lose {perda} s on average compared to your best lap.")
        motivos = []
        if c["freada_dif_m"] <= -8:
            motivos.append(tr(f"freia {abs(c['freada_dif_m']):.0f} m antes", f"brake {abs(c['freada_dif_m']):.0f} m earlier"))
        elif c["freada_dif_m"] >= 8:
            motivos.append(tr(f"freia {c['freada_dif_m']:.0f} m depois (e provavelmente passa do ponto)",
                              f"brake {c['freada_dif_m']:.0f} m later (and probably overshoot)"))
        if c["vmin_dif"] <= -4:
            motivos.append(tr(f"passa {abs(c['vmin_dif']):.0f} km/h mais lento no ápice",
                              f"are {abs(c['vmin_dif']):.0f} km/h slower at the apex"))
        elif c["vmin_dif"] >= 4:
            motivos.append(tr(f"entra {c['vmin_dif']:.0f} km/h mais rápido e perde na saída",
                              f"carry {c['vmin_dif']:.0f} km/h more into the corner and lose on exit"))
        if motivos:
            txt += tr(" Nas outras voltas você ", " On the other laps you ") + tr(" e ", " and ").join(motivos) + "."
        dicas.append(txt)
    return dicas


def _reduzir(amostras, melhor_serie=None):
    s = _serie(amostras)
    out, prox = [], 0.0
    dm = tm = None
    if melhor_serie:
        dm, tm = [a[0] for a in melhor_serie], [a[1] for a in melhor_serie]
    for a in s:
        if a[0] >= prox:
            delta = round((a[1] - _interp(dm, tm, a[0])) / 1000, 3) if dm else 0
            out.append([a[0], a[2], a[3], a[4], a[5], delta])
            prox = a[0] + PASSO_M
    return out


def gerar(sessao, caminho):
    tracos = sessao.tracos
    validas = {k: v for k, v in tracos.items() if v.get("comparavel", v["valida"]) and len(v["amostras"]) > 50}
    if not validas:
        validas = {k: v for k, v in tracos.items() if v["valida"] and len(v["amostras"]) > 50}
    n_melhor = min(validas, key=lambda k: validas[k]["tempo"])
    melhor = validas[n_melhor]
    outras = [v for k, v in validas.items() if k != n_melhor]
    curvas = _analisar(melhor, outras)
    serie_melhor = _serie(melhor["amostras"])
    voltas = {}
    for k, v in sorted(tracos.items()):
        if len(v["amostras"]) > 50:
            voltas[str(k)] = {"tempo": v["tempo"], "valida": v["valida"], "tipo": v.get("tipo", ""),
                              "pneu": v.get("pneu", ""), "serie": _reduzir(v["amostras"], serie_melhor)}
    mapa = [[a[6], a[7]] for a in serie_melhor[::4] if a[6] or a[7]]
    tf = sessao.mapa.tf if getattr(sessao, "mapa", None) is not None else None
    dados = {
        "pista": sessao.nome_pista, "sessao": sessao.nome_sessao, "data": sessao.inicio.strftime("%d/%m/%Y %H:%M"),
        "melhor": n_melhor, "voltas": voltas, "curvas": curvas, "dicas": _dicas(curvas), "mapa": mapa, "tf": tf,
        "gerado": datetime.now().strftime("%d/%m/%Y %H:%M"), "idioma": "en" if idioma.en() else "pt",
    }
    modelo = open(os.path.join(_raiz(), "relatorio_modelo.html"),
                  encoding="utf-8").read()
    html = modelo.replace("/*__DADOS__*/null", json.dumps(dados, ensure_ascii=False).replace("</", "<\\/"))
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(html)
    return caminho
