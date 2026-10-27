# -*- coding: utf-8 -*-
"""
Simulador de telemetria do F1 25 - para testar o engenheiro SEM o PS5.

Abra o engenheiro em uma janela e, em outra, rode:
    python simulador.py                 -> corrida curta em Mônaco (com Safety Car e chuva no fim)
    python simulador.py classificacao   -> Classificação 1 (zona de corte, minutos finais)

Opções: --formato 2025  (padrão 2026)   --velocidade 10  (quantas vezes mais rápido que o real)
"""

import base64
import math
import random
import socket
import struct
import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from f1_types import (PacketHeader, F1PacketType, LapData, PacketLapData,  # noqa: E402
                      CarTelemetryData, PacketCarTelemetryData, CarStatusData, PacketCarStatusData,
                      CarDamageData, PacketCarDamageData, ParticipantData, LiveryColour, PacketParticipantsData,
                      CarSetupData, PacketCarSetupData, CarMotionData, PacketMotionData)
try:
    from f1_types import CarTelemetry2Data, PacketCarTelemetry2Data  # noqa: E402
except ImportError:  # pragma: no cover
    PacketCarTelemetry2Data = None
from f1_types.common import get_num_cars  # noqa: E402

# Pacotes de sessão reais (F1 25 e F1 26), usados como base e ajustados pelo simulador.
S25 = "AAAABeMQDygAIBwgHFAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADIPcxDyD3MQ8g9zEMAAAAAAAAAAAAAAAAAAQAAAAADAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACtka1EYvhCRQ=="
S26 = "AiEXAwIXAQcNxwsQDjwAAP8ADpg+MD0Axb4LPgCj+TI+AGIRUj4AyceIPgC82Z4+ALMVvD4AjO7gPgBhHgA/AGyhGD8AIU8+PwBndVI/AMzBaD8A50V2PwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAALQEAAiECFwIRAQUCIQIXAhEBCgIhAhcCEQEPAiECFwIRAR4CIQIXAhABLQIhAhcCEAE8AiECFwIQAgACIgAYABECBQIiAhgCEwIKAiICGAIUAg8CIgIXARUCHgIhARcCGAItAiABFwIYAjwCHwEWARgDAAIlABkAEQMFAiUCGQITAwoCJQIZAhQDDwIlAhkCFQMeAiUCGQIYAy0CJQIZAhgDPAIlAhkCGAUAAiABFwIRBQUCIAIXAhEFCgIgAhcCEQUPAiACFwISBRQCIAIXAhIGAAIgARcCEQYFAiACFwIRBgoCIAIXAhEGDwIgAhcCEgYUAiACFwISBwACIAEXAhEHBQIgAhcCEQcKAiACFwIRBw8CIAIXAhIHFAIgAhcCEg8AAiQAGQAXDwUCJAIZAhcPCgIkAhkCFw8PAiQCGQIWDx4CJAIZAhYPLQIkAhkCFQ88AiQCGQIVD1oCIwEYARMPeAIiARcBEwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAF5I0xTYSNMU2EjTFNgAAAAAAAEAAAAAAAAEAPcCAAAAAQABAAAAAAEBAQEBAAEAAQECAAAAAAECAwEA/wIAAQcBAgMFBgcPAAAAAAAfm+JEpiuGRQAET75+P/rHLT306WQ+vmqhPkVnzD51KP0+Egw5P9pTWD8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAMkOGU7+sctPRdfbz6+aqE+qKk7P9pTWD8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAvTpZD4KuqM+c6I2P1+qVT8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

DESTINO = ("127.0.0.1", 20777)
def id_equipe(nome):
    """Id de equipe do pacote 2026 do jogo para cada piloto (o seu carro é da Cadillac)."""
    import engenheiro
    ids = {v: k for k, v in engenheiro.ID_EQUIPE.items() if k >= 476}
    eq = engenheiro.equipe_do_nome(nome) or "cadillac"
    return ids.get(eq, 486)


PILOTOS = ["Player", "Verstappen", "Hadjar", "Sainz", "Piastri", "Norris", "Hamilton", "Leclerc",
           "Antonelli", "Ocon", "Russell", "Bortoleto", "Albon", "Gasly", "Hulkenberg", "Lawson",
           "Lindblad", "Stroll", "Alonso", "Bearman", "Colapinto", "Perez"]


class V:
    """Valor no formato de enum (o construtor da biblioteca usa .value)."""
    def __init__(self, v):
        self.value = v


def arg(nome, padrao):
    if nome in sys.argv:
        return type(padrao)(sys.argv[sys.argv.index(nome) + 1])
    return padrao


FORMATO = arg("--formato", 2026)
VELOC = arg("--velocidade", 10.0)
INCIDENTES = "--incidentes" in sys.argv     # corrida com abandono, toque, asa quebrada e volta lenta (sem SC/chuva)
DEMO = False                                # demonstração dentro do app: incidentes + Safety Car + chuva
PARAR_DEMO = None
CENARIO = "classificacao" if "classificacao" in sys.argv else ("treino" if "treino" in sys.argv else "corrida")
UID = random.getrandbits(63)
N = 22
JOG = 0
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
frame = 0


def cabecalho(tipo, t):
    global frame
    frame += 1
    return PacketHeader.from_values(FORMATO, FORMATO % 100, 1, 0, 1, tipo, UID, t, frame, frame, JOG, 255)


def completar(lista, vazio):
    """O jogo sempre manda o número máximo de carros (22 no F1 25, 24 no F1 26)."""
    return lista + [vazio] * (get_num_cars(FORMATO) - len(lista))


def enviar(pkt):
    sock.sendto(pkt.to_bytes(), DESTINO)


def sessao(t, tipo, pista, voltas, clima, t_restante, duracao, sc, previsao, pit_ideal=0, pit_lim=0):
    raw = bytearray(base64.b64decode(S26 if FORMATO >= 2026 else S25))
    raw[0] = clima
    raw[1] = 30
    raw[2] = 22
    raw[3] = voltas
    raw[6] = tipo
    raw[7] = pista
    comp = {5: 3337.0, 6: 4361.0}.get(pista, 5000.0)
    struct.pack_into("<H", raw, 4, int(comp))
    struct.pack_into("<ff", raw, 716, comp * 0.34, comp * 0.68)   # início do setor 2 e 3
    struct.pack_into("<HH", raw, 9, int(t_restante), int(duracao))
    raw[124] = sc
    raw[126] = len(previsao)
    for k, (st, off, cl, chuva) in enumerate(previsao):
        struct.pack_into("<BBBbbbbB", raw, 127 + 8 * k, st, off, cl, 30, 2, 22, 2, chuva)
    raw[653] = pit_ideal
    raw[654] = pit_lim
    sock.sendto(cabecalho(F1PacketType.SESSION, t).to_bytes() + bytes(raw), DESTINO)


def evento(t, codigo, detalhes=b""):
    sock.sendto(cabecalho(F1PacketType.EVENT, t).to_bytes() + codigo.encode() + detalhes, DESTINO)


class C:
    def __init__(self, i):
        self.i = i
        self.base = 74.0 + i * 0.12 + random.uniform(-0.1, 0.1)
        self.dist = -i * 12.0      # grid
        self.volta = 1
        self.tempos = []           # tempos de voltas completas (s)
        self.t_volta = 0.0
        self.s1 = self.s2 = 0
        self.pneu = 17
        self.idade = 0
        self.desg = 0.0
        self.pits = 0
        self.pit_status = 0
        self.resultado = 2
        self.invalida = 0
        self.melhor = 0
        self.parando = 0.0         # >0: perdendo velocidade até parar (abandono)
        self.asa = 0


def carregar_tracado(pista):
    try:
        import json
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mapas", f"pista_{pista}.json"),
                  encoding="utf-8") as f:
            return json.load(f)["pontos"]
    except (OSError, ValueError, KeyError):
        return None


def posicao_no_tracado(tracado, f):
    if not tracado:
        a = 2 * math.pi * f
        return 420 * math.cos(a) + 130 * math.cos(3 * a) + 40 * math.sin(5 * a), 260 * math.sin(a) + 90 * math.sin(2 * a)
    k = f * len(tracado)
    i = int(k) % len(tracado)
    j = (i + 1) % len(tracado)
    t = k - int(k)
    return (tracado[i][0] * (1 - t) + tracado[j][0] * t, tracado[i][1] * (1 - t) + tracado[j][1] * t)


def rodar():
    random.seed(7)
    corrida = CENARIO == "corrida"
    pista, comp = (5, 3337.0) if corrida else (6, 4361.0)
    total_voltas = 8 if corrida else 0
    tipo = 15 if corrida else (1 if CENARIO == "treino" else 5)
    duracao = 3600 if corrida else 18 * 60
    tracado = carregar_tracado(pista)
    carros = [C(i) for i in range(N)]
    eu = carros[JOG]
    eu.base = 74.3
    if corrida:
        for k, c in enumerate(carros):  # jogador larga em P5
            c.dist = -((k + 4) % N if k else 4) * 12.0
    else:
        for c in carros:
            c.dist = -random.uniform(0, comp)
    t = 0.0
    dt = 0.1          # segundos simulados por passo
    passo_real = dt / VELOC
    clima = 0
    sc = 0
    pen = 0
    adv = 0
    dano_asa = 0
    eu_garagem = False
    previsao = [(tipo, 0, 0, 10), (tipo, 5, 0, 20), (tipo, 8, 3, 70), (tipo, 15, 3, 80)] if corrida else \
               [(tipo, 0, 0, 5), (tipo, 10, 0, 5)]
    evento(0, "SSTA")
    fim = False
    ultimo_lento = 0
    while not fim:
        t += dt
        # ---- roteiro ----
        ordem_ant = sorted(carros, key=lambda c: -c.dist)
        if corrida and INCIDENTES:
            pe = ordem_ant.index(eu)
            if eu.dist / comp >= 1.6 and not getattr(rodar, "coll", False) and pe >= 2:
                rodar.coll = True     # toque entre os dois carros logo à frente
                a, b = ordem_ant[pe - 1], ordem_ant[pe - 2]
                evento(t, "COLL", struct.pack("<BBB", a.i, b.i, 1) if FORMATO >= 2026 else struct.pack("<BB", a.i, b.i))
                a.asa = 45
            if eu.dist / comp >= 2.3 and not getattr(rodar, "quebra", False):
                rodar.quebra = ordem_ant[min(len(ordem_ant) - 1, pe + 3)]     # 3 posições atrás: falha mecânica
                rodar.quebra.parando = t
            if eu.volta == 4 and not getattr(rodar, "lento", None):
                cand = [c for c in carros if c.i % 3 == 2 and c is not eu and c.resultado == 2]
                rodar.lento = min(cand, key=lambda c: abs(ordem_ant.index(c) - pe))
                rodar.lento_volta = rodar.lento.volta + 1
                print(f"  carro lento: {PILOTOS[rodar.lento.i]} na volta {rodar.lento_volta}", flush=True)
        if corrida and (not INCIDENTES or DEMO):
            sc = 1 if (3.2 <= eu.dist / comp <= 3.9) else 0
            if 3.85 <= eu.dist / comp <= 3.9 and not getattr(rodar, "sc_ev", False):
                rodar.sc_ev = True
                evento(t, "SCAR", struct.pack("<BB", 1, 1))
            clima = 3 if eu.dist / comp >= 6.0 and (not INCIDENTES or DEMO) else 0
            if eu.dist / comp >= 1.5:
                adv = 1
                dano_asa = 30
            if eu.dist / comp >= 4.5:
                pen = 5
        # ---- movimento ----
        for c in carros:
            if c.resultado == 3:
                continue
            ritmo = c.base + 0.08 * c.desg
            if c.resultado == 7:
                continue
            if c.parando:
                if t - c.parando > 12:
                    c.resultado = 7
                    evento(t, "RTMT", struct.pack("<BB", c.i, 8))
                    continue
                ritmo *= 1 + (t - c.parando) * 3
            frac_c = (max(c.dist, 0) % comp) / comp
            if c is getattr(rodar, "lento", None) and c.volta == rodar.lento_volta and 1 / 3 < frac_c < 2 / 3:
                ritmo += 12
            if corrida and sc:
                ritmo *= 1.4
            if corrida and clima >= 3:
                ritmo += 0.3 if c.pneu == 7 else (4.0 if c is eu else 3.5)
            if not corrida and c is eu and eu_garagem:
                continue
            v = comp / ritmo
            c.dist += v * dt
            if c.dist < 0:
                continue
            c.t_volta += dt
            frac = (c.dist % comp) / comp
            nv = int(c.dist // comp) + 1
            if frac > 1 / 3 and not c.s1:
                c.s1 = int(c.t_volta * 1000)
            if frac > 2 / 3 and not c.s2:
                c.s2 = int(c.t_volta * 1000) - c.s1
            if nv > c.volta:
                c.tempos.append(c.t_volta)
                if not c.invalida and (not c.melhor or c.t_volta < c.melhor):
                    c.melhor = c.t_volta
                c.volta, c.t_volta, c.s1, c.s2, c.invalida = nv, 0.0, 0, 0, 0
                c.idade += 1
                if c is eu:
                    eu.base = (74.3 if corrida else 73.9) + random.uniform(-0.3, 0.4)
                c.desg += 3.2 if c.pneu == 16 else 2.4
                c.pit_status = 0
                if corrida:
                    if c is eu and c.volta == (6 if INCIDENTES else 5) and c.pits == 0:
                        c.pit_status = 1
                    if c is not eu and c.volta == 4 + (c.i % 3) and c.pits == 0:
                        c.pit_status = 1
                    if c is not eu and c.volta >= 7 and c.pneu != 7 and c.i % 2:
                        c.pit_status = 1
                    if c.pit_status:
                        c.pits += 1
                        c.pneu = 7 if c.volta >= 7 else 18
                        c.idade = 0
                        c.desg = 0.0
                        c.dist -= comp * 0.25
                    if c.volta > total_voltas:
                        c.resultado = 3
                else:
                    if c is eu and c.volta == 3:
                        c.invalida = 0
                    if c is eu and len(c.tempos) >= 4:
                        eu_garagem = True
            if not corrida and c is eu and c.volta == 2 and frac > 0.5:
                c.invalida = 1
        if corrida and eu.resultado == 3 and all(c.resultado == 3 or c.dist < eu.dist - comp for c in carros):
            fim = True
        t_restante = max(0, duracao - t)
        if not corrida:
            if t_restante <= 200 and eu_garagem:
                eu_garagem = False
                eu.base = 73.6
            if t_restante <= 0:
                fim = True

        ordem = sorted(carros, key=lambda c: -c.dist)
        pos = {c.i: k + 1 for k, c in enumerate(ordem)}
        if not corrida:
            ordem = sorted(carros, key=lambda c: c.melhor or 999)
            pos = {c.i: k + 1 for k, c in enumerate(ordem)}

        # ---- pacotes ----
        passo = int(round(t / dt))
        lds = []
        for c in carros:
            k = pos[c.i]
            frente = ordem[k - 2] if k > 1 else None
            dif = (frente.dist - c.dist) / (comp / c.base) if (frente and corrida) else 0
            lider = (ordem[0].dist - c.dist) / (comp / c.base) if corrida else 0
            frac = (max(c.dist, 0) % comp)
            setor = 0 if frac < comp / 3 else (1 if frac < 2 * comp / 3 else 2)
            ultima = int(c.tempos[-1] * 1000) if c.tempos else 0
            st_piloto = 0 if (not corrida and c is eu and eu_garagem) else (1 if not corrida else 4)
            lds.append(LapData.from_values(
                ultima, int(c.t_volta * 1000), c.s1 % 60000, c.s1 // 60000, c.s2 % 60000, c.s2 // 60000,
                int(dif * 1000) % 60000, int(dif * 1000) // 60000, int(lider * 1000) % 60000,
                int(lider * 1000) // 60000, frac, c.dist, 0.0, k, c.volta, c.pit_status, c.pits, setor,
                c.invalida, pen if c is eu else 0, adv if c is eu else 0, adv if c is eu else 0, 0, 0,
                5 if c is eu else c.i + 1, st_piloto, c.resultado, 0, 0, 0, 0, 0.0, 0, packet_format=FORMATO))
        vazio = LapData.from_values(*([0] * 10), 0.0, 0.0, 0.0, *([0] * 18), 0.0, 0, packet_format=FORMATO)
        enviar(PacketLapData.from_values(cabecalho(F1PacketType.LAP_DATA, t), completar(lds, vazio)))

        tels = []
        for c in carros:
            fr = (max(c.dist, 0) % comp) / comp + (c.volta % 3) * 0.003
            curva = abs(((fr * 7) % 1) - 0.5) < 0.12
            vel = 120 if curva else 270
            if c.parando:
                vel = max(0, int(270 - (t - c.parando) * 60))
            tels.append(CarTelemetryData.from_values(
                vel, 0.4 if curva else 1.0, 0.3 if curva else 0.0, 0.6 if curva else 0.0, 0, 3 if curva else 7,
                11000, False, 50, 0, 500, 500, 600, 600, 95, 95, 92, 92, 100, 100, 98, 98, 105,
                21.5, 21.5, 24.0, 24.0, 0, 0, 0, 0, packet_format=FORMATO))
        movs = []
        for c in carros:
            f = (max(c.dist, 0) % comp) / comp
            x, z = posicao_no_tracado(tracado, f)
            if c.pit_status:
                z -= 25
            movs.append(CarMotionData.from_values(x, 5.0, z, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                                                  packet_format=FORMATO))
        enviar(PacketMotionData.from_values(cabecalho(F1PacketType.MOTION, t), completar(movs, movs[-1])))
        enviar(PacketCarTelemetryData.from_values(cabecalho(F1PacketType.CAR_TELEMETRY, t),
                                                  completar(tels, tels[-1]), 0, 255, 0))

        if passo % 5 == 0:
            sts = [CarStatusData.from_values(V(2), True, V(1), 56, False, 30.0 - c.dist / comp * 3.6, 110.0, 0.4,
                                             13000, 4000, 8, 0, 0, V(17), V(c.pneu), c.idade, V(0), 500000.0,
                                             120000.0, 3.0e6, V(1), 0.0, 0.0, 0.0, 0, packet_format=FORMATO)
                   for c in carros]
            enviar(PacketCarStatusData.from_values(cabecalho(F1PacketType.CAR_STATUS, t), completar(sts, sts[-1])))
            dns = [CarDamageData.from_values(FORMATO, [c.desg * 1.05, c.desg * 1.1, c.desg * 0.8, c.desg * 0.82],
                                             [0] * 4, [0] * 4, [0] * 4, dano_asa if c is eu else c.asa, 0, 0, 0, 0, 0,
                                             False, False, 60, 0, 0, 67, 14, 52, 30, min(100, 67 + c.volta),
                                             False, False) for c in carros]
            enviar(PacketCarDamageData.from_values(cabecalho(F1PacketType.CAR_DAMAGE, t), completar(dns, dns[-1])))
            if PacketCarTelemetry2Data is not None and FORMATO >= 2026:
                t2 = []
                for c in carros:
                    fr = (max(c.dist, 0) % comp) / comp
                    disp = corrida and 0.10 < fr < 0.30
                    t2.append(CarTelemetry2Data.from_values(1 if 0.05 < fr < 0.2 else 0, True, 0, disp, False,
                                                            int((0.10 - fr) * comp) if 0.02 < fr < 0.10 else 0,
                                                            True, False))
                enviar(PacketCarTelemetry2Data.from_values(cabecalho(F1PacketType.CAR_TELEMETRY_2, t),
                                                           completar(t2, t2[-1])))
        if passo % 10 == 0:
            sessao(t, tipo, pista, total_voltas, clima, t_restante, duracao, sc, previsao, 6 if corrida else 0,
                   8 if corrida else 0)
            cab = cabecalho(F1PacketType.PARTICIPANTS, t)
            cores = [LiveryColour.from_values(200, 30, 30)] * 4
            parts = [ParticipantData.from_values(cab, k != JOG, k, 255, V(id_equipe(PILOTOS[k])), False, k + 1, V(1), PILOTOS[k], V(1),
                                                 True, V(0), 0, 4, cores) for k in range(N)]
            enviar(PacketParticipantsData.from_values(cab, N, completar(parts, parts[-1])))
            acertos = [CarSetupData.from_values(FORMATO, 23, 20, 45, 55, -3.1, -1.3, 0.02, 0.17, 33, 6, 11, 5, 25,
                                                50, 100, 56, 22.0, 22.0, 24.5, 24.5, 0, 32.0)] * N
            enviar(PacketCarSetupData.from_values(cabecalho(F1PacketType.CAR_SETUPS, t), completar(acertos, acertos[-1])))
        # botões "Ação UDP" do controle: 1 na volta 3, 2 na volta 5, 3 na volta 6
        for volta_b, acao in ((3, 1), (5, 2), (6, 3)):
            chave = f"botao{acao}"
            if eu.volta == volta_b and not getattr(rodar, chave, False) and (corrida or acao == 1):
                setattr(rodar, chave, True)
                evento(t, "BUTN", struct.pack("<I", 0x00100000 << (acao - 1)))
                evento(t + 0.1, "BUTN", struct.pack("<I", 0))
        if corrida and eu.volta == 2 and passo % 10 == 0 and not getattr(rodar, "ftlp", False):
            rodar.ftlp = True
            evento(t, "FTLP", struct.pack("<Bf", JOG, 74.1))
        if PARAR_DEMO is not None and PARAR_DEMO.is_set():
            return
        if int(t) % 30 == 0 and int(t) != ultimo_lento and not DEMO:
            ultimo_lento = int(t)
            print(f"  simulado {t:6.0f}s  volta {eu.volta}  P{pos[JOG]}", flush=True)
        time.sleep(passo_real)
    evento(t, "CHQF")
    evento(t, "SEND")
    print("Simulação terminada.")


def preparar_demo(cenario, porta, nome_piloto, parar):
    """Prepara a demonstração que o app roda sozinho (sem o jogo). Devolve o id da sessão simulada."""
    global CENARIO, VELOC, INCIDENTES, DEMO, PARAR_DEMO, DESTINO, UID
    CENARIO = cenario if cenario in ("corrida", "classificacao", "treino") else "corrida"
    VELOC = 3.0 if CENARIO == "corrida" else 6.0
    INCIDENTES = DEMO = True
    PARAR_DEMO = parar
    DESTINO = ("127.0.0.1", int(porta))
    UID = random.getrandbits(63) or 1
    PILOTOS[JOG] = str(nome_piloto or "Você")[:40]
    for k in list(vars(rodar)):        # o roteiro guarda marcas na própria função: limpa para rodar de novo
        delattr(rodar, k)
    return UID


def rodar_demo():
    try:
        rodar()
    except Exception as e:  # noqa: BLE001
        print(f"[DEMO] Erro na demonstração: {e}", flush=True)


if __name__ == "__main__":
    print(f"Simulando {CENARIO} (formato {FORMATO}) -> {DESTINO[0]}:{DESTINO[1]}")
    rodar()
