# -*- coding: utf-8 -*-
"""Falas do engenheiro: variações de frases, dicas por pista e mensagens de resultado (português e inglês)."""

import random

from idioma import L, en

PONTOS_GP = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
PONTOS_SPRINT = [8, 7, 6, 5, 4, 3, 2, 1]

# id da pista -> ((onde ultrapassar, dica) em português, (onde ultrapassar, dica) em inglês)
PISTAS = {
    0: (("na freada da curva 3 e da curva 11", "a chicane das curvas 9 e 10 é rápida: cuidado com as zebras"),
        ("into turn 3 and turn 11", "the turn 9 and 10 chicane is fast: careful with the kerbs")),
    2: (("no grampo da curva 14, depois da reta enorme", "a curva 1 é longa e fechando: não acelere cedo demais"),
        ("into the turn 14 hairpin, after the long straight", "turn 1 is long and tightening: don't get on the power too early")),
    3: (("na freada da curva 1 e da curva 4", "o asfalto é abrasivo: poupe os traseiros na saída das curvas lentas"),
        ("into turn 1 and turn 4", "the tarmac is abrasive: look after the rears out of the slow corners")),
    4: (("na freada da curva 1", "as curvas 3 e 9 castigam o dianteiro esquerdo: acelerador progressivo"),
        ("into turn 1", "turns 3 and 9 punish the front left: be progressive on the throttle")),
    5: (("na chicane depois do túnel", "aqui a posição vale ouro: sem riscos no muro"),
        ("into the chicane after the tunnel", "track position is everything here: no risks near the wall")),
    6: (("na freada do grampo e na chicane final", "cuidado com o muro dos campeões na saída da última chicane"),
        ("into the hairpin and the final chicane", "watch the Wall of Champions on the exit of the last chicane")),
    7: (("na freada da Stowe e na Brooklands", "Maggots e Becketts pedem ritmo, sem frear demais"),
        ("into Stowe and Brooklands", "Maggotts and Becketts need rhythm, don't over-brake")),
    9: (("na freada da curva 1", "pista travada: a classificação decide muito"),
        ("into turn 1", "tight track: qualifying decides a lot")),
    10: (("na reta Kemmel, freando para a Les Combes", "a Eau Rouge sai de pé embaixo se a entrada for limpa"),
         ("on the Kemmel straight, braking for Les Combes", "Eau Rouge is flat out if you get a clean exit from turn 1")),
    11: (("na freada da primeira chicane", "a saída da Parabólica define a reta: priorize a tração"),
         ("into the first chicane", "the Parabolica exit defines the straight: prioritise traction")),
    12: (("na freada da curva 7 e da curva 14", "muro perto em todo lugar e pista quente: poupe os traseiros"),
         ("into turn 7 and turn 14", "walls everywhere and a hot track: look after the rears")),
    13: (("na freada da curva 1 e na chicane final", "os Esses pedem ritmo: uma linha limpa vale mais que frear tarde"),
         ("into turn 1 and the final chicane", "the Esses need rhythm: a clean line beats late braking")),
    14: (("na freada do grampo da curva 9 e da curva 5", "a última parte é lenta: tração na saída das curvas"),
         ("into the turn 9 hairpin and turn 5", "the last part is slow: focus on traction on exit")),
    15: (("na subida da curva 1 e na curva 12, no fim da reta", "os Esses do primeiro setor pedem ritmo"),
         ("up the hill into turn 1 and into turn 12 at the end of the straight", "the first sector Esses need rhythm")),
    16: (("no S do Senna e na Descida do Lago", "a Junção define a reta dos boxes: saia bem dela"),
         ("into the Senna S and Descida do Lago", "Junção defines the main straight: nail the exit")),
    17: (("na freada da curva 3 e da curva 4", "as zebras de saída gastam pneu e podem invalidar a volta"),
         ("into turn 3 and turn 4", "the exit kerbs eat tyres and can invalidate your lap")),
    19: (("na freada da curva 1, depois da reta enorme", "o ar rarefeito esquenta freios e motor"),
         ("into turn 1, after the long straight", "the thin air heats up brakes and engine")),
    20: (("na curva 1 e na freada da curva 3", "a parte do castelo é estreita: sem riscos no muro"),
         ("into turn 1 and turn 3", "the castle section is narrow: no risks near the wall")),
    26: (("na freada da Tarzan, na curva 1", "a última curva é inclinada: dá para acelerar cedo"),
         ("into Tarzan, turn 1", "the last corner is banked: you can get on the power early")),
    27: (("na freada da Tamburello e da Rivazza", "zebras altas nas chicanes: não exagere"),
         ("into Tamburello and Rivazza", "high kerbs in the chicanes: don't overdo it")),
    29: (("na curva 1 e no grampo da curva 27", "pista rápida entre muros: constância vale mais que risco"),
         ("into turn 1 and the turn 27 hairpin", "fast track between walls: consistency beats risk")),
    30: (("no grampo da curva 11 e na curva 17", "a chicane lenta das curvas 14 e 15 é traiçoeira"),
         ("into the turn 11 hairpin and turn 17", "the slow turn 14 and 15 chicane is tricky")),
    31: (("na freada da curva 14, depois da Strip", "pista fria: aqueça bem os pneus"),
         ("into turn 14, after the Strip", "cold track: get the tyres warm")),
    32: (("na freada da curva 1", "curvas rápidas o tempo todo: os pneus sofrem muito"),
         ("into turn 1", "fast corners everywhere: the tyres suffer a lot")),
}


def num(v, casas=3):
    """Compatibilidade: diferença de tempo falada do jeito natural."""
    return dif(v)


def _dif_en(s):
    if s < 0.0005:
        return "zero"
    if s < 0.095:
        ms = max(1, round(s * 1000))
        return f"{ms} thousandth{'s' if ms > 1 else ''}"
    if s < 0.95:
        d = round(s * 10)
        if d == 5:
            return "half a second"
        return f"{d} tenth{'s' if d > 1 else ''}"
    if s < 9.95:
        v = round(s, 1)
        if v == int(v):
            return f"{int(v)} second{'s' if int(v) != 1 else ''}"
        return f"{v:.1f} seconds"
    return f"{round(s)} seconds"


def dif(seg):
    """Diferença de tempo falada como no rádio: '45 milésimos', '3 décimos', 'meio segundo',
    '1 segundo e 4 décimos', '12 segundos' (ou em inglês: '3 tenths', '1.4 seconds')."""
    s = abs(float(seg))
    if en():
        return _dif_en(s)
    if s < 0.0005:
        return "zero"
    if s < 0.095:
        ms = max(1, round(s * 1000))
        return f"{ms} milésimo{'s' if ms > 1 else ''}"
    if s < 0.95:
        d = round(s * 10)
        if d == 5:
            return "meio segundo"
        return f"{d} décimo{'s' if d > 1 else ''}"
    if s < 9.95:
        inteiro, d = int(s), round((s - int(s)) * 10)
        if d == 10:
            inteiro, d = inteiro + 1, 0
        txt = f"{inteiro} segundo{'s' if inteiro > 1 else ''}"
        if d == 5:
            return txt + " e meio"
        return txt + (f" e {d} décimo{'s' if d > 1 else ''}" if d else "")
    return f"{round(s)} segundos"


def gap(seg):
    """Distância para outro carro (mesmo formato de dif)."""
    return dif(seg)


def tempo(ms):
    """Tempo de volta: 69845 -> '1 minuto, 9 segundos e 845' / '1 minute 9 point 8 4 5'."""
    if not ms or ms <= 0:
        return L("sem tempo", "no time")
    m, resto = divmod(int(ms), 60000)
    s, mil = divmod(resto, 1000)
    if en():
        frac = " ".join(f"{mil:03d}")
        seg = f"{s} point {frac}"
        return f"{m} minute{'s' if m > 1 else ''} {seg}" if m else f"{seg} seconds"
    seg = f"{s} segundo{'s' if s != 1 else ''} e {mil if mil >= 100 else str(mil) + ' milésimos'}"
    return f"{m} minuto{'s' if m > 1 else ''}, {seg}" if m else seg


def voltas(v):
    """Voltas de combustível: 0.4 -> 'meia volta' / 'half a lap', 1.5 -> '1 volta e meia' / '1 and a half laps'."""
    r = round(abs(float(v)) * 2) / 2
    inteiro = int(r)
    if en():
        if r == 0:
            return "less than half a lap"
        if r == 0.5:
            return "half a lap"
        if r - inteiro:
            return f"{inteiro} and a half laps"
        return f"{inteiro} lap{'s' if inteiro > 1 else ''}"
    if r == 0:
        return "menos de meia volta"
    if r == 0.5:
        return "meia volta"
    base = f"{inteiro} volta{'s' if inteiro > 1 else ''}"
    return base + (" e meia" if r - inteiro else "")


def escolher(*opcoes):
    return random.choice(opcoes)


def _pista(pista):
    par = PISTAS.get(pista)
    if not par:
        return L(("na freada da curva 1", ""), ("into turn 1", ""))
    return par[1] if en() else par[0]


def ultrapassagem(pista):
    return _pista(pista)[0]


def dica(pista):
    return _pista(pista)[1]


def largada(pos, pista, total):
    if en():
        alvo = ("We can win this today." if pos <= 3 else
                "The podium is the target." if pos <= 6 else
                "Let's go for good points." if pos <= 10 else
                "We can get into the points.")
        txt = f"Starting from P{pos}. {alvo} The best place to overtake here is {ultrapassagem(pista)}."
        if pos >= 8:
            txt += " No risks at the start: it's a long race."
        return txt
    alvo = ("A vitória é possível hoje." if pos <= 3 else
            "Pódio é o objetivo." if pos <= 6 else
            "Vamos buscar bons pontos." if pos <= 10 else
            "Dá para entrar na zona de pontos.")
    txt = f"Largando de P{pos}. {alvo} A melhor chance de ultrapassar aqui é {ultrapassagem(pista)}."
    if pos >= 8:
        txt += " Na largada, sem riscos: a corrida é longa."
    return txt


def depois_da_largada(grid, pos, pista):
    """Dito uns segundos depois da largada, no lugar do "largando de P5" (quando não houve volta de apresentação).
    O ganho de posições fica para o fim da primeira volta."""
    if en():
        return (f"Start done, P{pos}. " if pos else "Start done. ") + f"The best place to overtake here is {ultrapassagem(pista)}."
    return (f"Largada feita, P{pos}. " if pos else "Largada feita. ") + f"A melhor chance de ultrapassar aqui é {ultrapassagem(pista)}."


def fim_corrida(pos, largada_pos, sprint, volta_rapida):
    """sprint=None quando não dá para saber se foi sprint (aí não fala de pontos)."""
    pts_tab = PONTOS_SPRINT if sprint else PONTOS_GP
    pts = pts_tab[pos - 1] if 1 <= pos <= len(pts_tab) else 0
    vr = L(" E ainda fez a volta mais rápida!", " And the fastest lap too!")
    if sprint is None and pos > 3:
        pts = 0
        if pos <= 10:
            return f"P{pos}. " + L("Bom resultado.", "Good result.") + _posicoes(pos, largada_pos) + (vr if volta_rapida else "")
    if pos == 1:
        txt = L(escolher("Vitória! Você venceu! Que corrida!", "P1! Vitória! Trabalho fantástico hoje!",
                         "Vencemos! Que pilotagem!"),
                escolher("You win! Get in there! What a race!", "P1! Race win! Fantastic job today!",
                         "We won it! Brilliant driving!"))
    elif pos <= 3:
        txt = L(escolher(f"P{pos}! Pódio! Excelente corrida!", f"É pódio! P{pos}! Muito bem!"),
                escolher(f"P{pos}! Podium! Excellent race!", f"That's a podium! P{pos}! Well done!"))
    elif pts:
        txt = L(f"P{pos}. {pts} {'ponto' if pts == 1 else 'pontos'} para a equipe. Bom trabalho.",
                f"P{pos}. {pts} {'point' if pts == 1 else 'points'} for the team. Good job.")
    else:
        txt = L(escolher(f"P{pos}. Fora dos pontos hoje, mas tem coisa boa para levar daqui.",
                         f"P{pos}. Não deu pontos hoje. Vamos analisar e voltar mais fortes."),
                escolher(f"P{pos}. No points today, but there are positives to take away.",
                         f"P{pos}. Not our day. We'll analyse it and come back stronger."))
    txt += _posicoes(pos, largada_pos)
    if volta_rapida:
        txt += vr
    return txt


def _posicoes(pos, largada_pos):
    if not largada_pos or largada_pos == pos:
        return ""
    d = largada_pos - pos
    if d > 0:
        return L(f" Ganhou {d} {'posição' if d == 1 else 'posições'} desde a largada.",
                 f" Gained {d} {'place' if d == 1 else 'places'} from the start.")
    return L(f" Perdeu {-d} {'posição' if d == -1 else 'posições'} desde a largada.",
             f" Lost {-d} {'place' if d == -1 else 'places'} from the start.")


def fim_classificacao(tipo, pos, n_carros, dif_pole, dif_corte, corte, setor_fraco):
    """tipo: 'q1' / 'q2' / 'final' (Q3, classificação curta ou de volta única)."""
    if tipo in ("q1", "q2"):
        prox = "Q2" if tipo == "q1" else "Q3"
        if pos <= corte:
            txt = L(escolher(f"Passamos para o {prox}. P{pos}.", f"Estamos no {prox}! Fechou em P{pos}."),
                    escolher(f"We're through to {prox}. P{pos}.", f"Into {prox}! P{pos}."))
        else:
            txt = L(f"Eliminado em P{pos}.", f"Out in P{pos}.")
            if dif_corte:
                txt += L(f" Faltaram {dif(dif_corte)} para o P{corte}.", f" We missed P{corte} by {dif(dif_corte)}.")
    else:
        if pos == 1:
            txt = L(escolher("Pole position! Volta perfeita!", "É pole! P1! Que volta!"),
                    escolher("Pole position! Perfect lap!", "That's pole! P1! What a lap!"))
        elif pos == 2:
            txt = L("P2, primeira fila!", "P2, front row!")
        elif pos <= 4:
            txt = L(f"P{pos}, segunda fila. Ótima posição.", f"P{pos}, second row. Great position.")
        elif pos <= 10:
            txt = L(f"P{pos} no grid. Boa base para buscar pontos.", f"P{pos} on the grid. A good base for points.")
        else:
            txt = L(f"P{pos} no grid.", f"P{pos} on the grid.")
        if pos > 1 and dif_pole:
            txt += L(f" A pole ficou a {dif(dif_pole)}.", f" Pole was {dif(dif_pole)} away.")
    passou = tipo in ("q1", "q2") and pos <= corte
    if setor_fraco and pos > 1 and not passou:
        txt += L(f" O tempo que faltou estava no setor {setor_fraco}.", f" The missing time was in sector {setor_fraco}.")
    elif setor_fraco and passou:
        txt += L(f" Para a próxima parte, dá para ganhar no setor {setor_fraco}.",
                 f" For the next part, there's time to gain in sector {setor_fraco}.")
    return txt


# ---------------- mudanças de posição na corrida ----------------

def ultrapassei(nome, pos, prox_nome, prox_gap, tras_gap, faltam):
    """Ultrapassagem confirmada na pista."""
    if en():
        txt = (escolher(f"Great move on {nome}!", f"Yes! Get in there, past {nome}!", f"Clean move on {nome}, well done!")
               if nome else escolher("Great move!", "Yes! Nice overtake!", "Clean move, well done!"))
        txt += f" P{pos}."
        if tras_gap is not None and tras_gap < 1.0:
            txt += escolher(" He still has Overtake: protect the next braking zone.",
                            " He's right behind: cover the inside into the next braking zone.")
        elif faltam is not None and faltam <= 2:
            txt += " Now bring it home."
        elif prox_nome and prox_gap is not None and prox_gap < 1.5:
            txt += f" Next target: {prox_nome}, {gap(prox_gap)} ahead."
        else:
            txt += escolher(" Now build a gap.", " Now get more than 1 second on him.")
        return txt
    if nome:
        txt = escolher(f"Bela ultrapassagem em {nome}!", f"Isso! Para cima de {nome}!",
                       f"Manobra limpa em {nome}, muito bem!", f"Boa! Passou {nome}!")
    else:
        txt = escolher("Bela ultrapassagem!", "Isso! Boa manobra!", "Manobra limpa, muito bem!")
    txt += f" P{pos}."
    if tras_gap is not None and tras_gap < 1.0:
        txt += escolher(" Ele ainda tem Overtake: proteja a próxima freada.",
                        " Ele está colado: segure a linha por dentro na próxima freada.")
    elif faltam is not None and faltam <= 2:
        txt += " Agora segura até a bandeirada."
    elif prox_nome and prox_gap is not None and prox_gap < 1.5:
        txt += f" Próximo alvo: {prox_nome}, a {gap(prox_gap)}."
    else:
        txt += escolher(" Agora abre vantagem.", " Agora abra mais de 1 segundo para ele.")
    return txt


def varias_ultrapassagens(qtd, pos):
    return L(escolher(f"Que sequência! Ganhou {qtd} posições. P{pos}.",
                      f"Excelente! Mais {qtd} posições. Estamos em P{pos}."),
             escolher(f"What a run! {qtd} places gained. P{pos}.", f"Excellent! {qtd} more places. We're P{pos}."))


def ultrapassado(nome, pos, motivo, gap_s, faltam, pista):
    """Perdeu a posição na pista. motivo: 'pneu' (ele tem pneu bem mais novo/mole), 'erro' (não houve ultrapassagem) ou ''."""
    if en():
        quem = nome or "The car behind"
        if motivo == "erro":
            return f"We lost the place{' to ' + nome if nome else ''}. P{pos}. Breathe and get the rhythm back."
        txt = escolher(f"{quem} is through. P{pos}.", f"We lost the place{' to ' + nome if nome else ''}. P{pos}.")
        if motivo == "pneu":
            txt += escolher(" He's on much fresher tyres, don't waste yours fighting. Focus on your pace.",
                            " His tyres are much better right now, let him go. Our race is with the others.")
        elif faltam is not None and faltam <= 3 and gap_s is not None and gap_s < 1.0:
            txt += f" Still on! Stay within 1 second, use Overtake and attack {ultrapassagem(pista)}."
        elif gap_s is not None and gap_s < 1.0:
            txt += escolher(f" Stay within 1 second to get Overtake. Your chance is {ultrapassagem(pista)}.",
                            " Stay close, the chance to get it back will come.")
        else:
            txt += escolher(" No problem, keep your pace and wait for his mistake.",
                            " Stay calm, it's a long race. We'll work on the gap.")
        return txt
    quem = nome or "O carro de trás"
    if motivo == "erro":
        return f"Perdemos a posição{' para ' + nome if nome else ''}. P{pos}. Respira e recupera o ritmo."
    txt = escolher(f"{quem} passou. P{pos}.", f"Perdemos a posição{' para ' + nome if nome else ''}. P{pos}.")
    if motivo == "pneu":
        txt += escolher(" Ele está com pneus bem mais novos, não gaste os seus brigando. Foco no seu ritmo.",
                        " Pneu dele é muito melhor agora, deixe ir. A nossa corrida é com os outros.")
    elif faltam is not None and faltam <= 3 and gap_s is not None and gap_s < 1.0:
        txt += f" Ainda dá! Fique a menos de 1 segundo, use o Overtake e ataque {ultrapassagem(pista)}."
    elif gap_s is not None and gap_s < 1.0:
        txt += escolher(f" Fique a menos de 1 segundo para ter o Overtake. A chance é {ultrapassagem(pista)}.",
                        " Fique colado nele, a chance de devolver vai aparecer.")
    else:
        txt += escolher(" Sem problema, mantenha o ritmo e espere o erro dele.",
                        " Calma, corrida longa. Vamos trabalhar a diferença.")
    return txt


def perdeu_varias(qtd, pos):
    return L(f"Perdemos {qtd} posições. P{pos}. Respira, uma curva de cada vez, e recupera o ritmo.",
             f"We lost {qtd} places. P{pos}. Breathe, one corner at a time, and get the rhythm back.")


def ganhou_sem_ultrapassar(nomes_box, nomes_fora, pos):
    if nomes_fora:
        if en():
            quem = nomes_fora[0] or "A car ahead"
            return f"{quem} {'has retired' if len(nomes_fora) == 1 else 'and others have retired'}. Up to P{pos}."
        quem = nomes_fora[0] or "Um carro à frente"
        return f"{quem} {'abandonou' if len(nomes_fora) == 1 else 'e outros abandonaram'}. Subimos para P{pos}."
    if nomes_box:
        quem = nomes_box[0] or L("O carro da frente", "The car ahead")
        return L(f"{quem} foi para os boxes. Subimos para P{pos}.", f"{quem} has pitted. Up to P{pos}.")
    return L(f"Ganhamos posição. P{pos}.", f"Place gained. P{pos}.")


def volta_do_box(pos, frente_nome, frente_gap, tras_nome, tras_gap, parou=True):
    if en():
        txt = f"{'Good stop. ' if parou else ''}We're out in P{pos}."
        if frente_nome and frente_gap is not None and frente_gap < 5:
            txt += f" {frente_nome} ahead, {gap(frente_gap)}."
        if tras_nome and tras_gap is not None and tras_gap < 2:
            txt += f" {tras_nome} right behind, {gap(tras_gap)}: careful on cold tyres."
        elif tras_gap is not None and tras_gap >= 2:
            txt += " Clear behind, get the tyres warm."
        return txt
    txt = f"{'Parada feita. ' if parou else ''}Voltamos em P{pos}."
    if frente_nome and frente_gap is not None and frente_gap < 5:
        txt += f" {frente_nome} à frente, a {gap(frente_gap)}."
    if tras_nome and tras_gap is not None and tras_gap < 2:
        txt += f" {tras_nome} logo atrás, a {gap(tras_gap)}: cuidado com os pneus frios."
    elif tras_gap is not None and tras_gap >= 2:
        txt += " Pista livre atrás, aqueça bem os pneus."
    return txt
