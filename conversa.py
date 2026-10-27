# -*- coding: utf-8 -*-
"""
Perguntas livres para o engenheiro (português ou inglês), sem internet e sem IA.

Entende do que você está falando por palavras-chave e por nomes de pilotos (inclusive do jeito que a gente
fala: "Rássel", "Leclér", "Verstápen") e responde com os dados ao vivo da telemetria.
Exemplos: "quanto falta pro Verstappen?", "o Leclerc já parou?", "dá pra ir até o fim com esse pneu?",
"onde eu tô perdendo tempo?", "o carro tá saindo de frente na entrada", "e se entrar Safety Car?".
In English: "what's the gap to Verstappen?", "has Leclerc pitted?", "will the tyres make it to the end?",
"where am I losing time?", "I have understeer on entry", "what if there's a Safety Car?".
As palavras-chave dos dois idiomas valem sempre; a resposta sai no idioma escolhido.
"""

import difflib
import re
import unicodedata

import falas
from idioma import L as tr

# jeitos de falar o nome -> nome como vem no jogo (sem acento, minúsculo)
APELIDOS = {
    "rassel": "russell", "russel": "russell", "leclair": "leclerc", "lecler": "leclerc", "leclerque": "leclerc",
    "verstapen": "verstappen", "verstappe": "verstappen", "max": "verstappen", "rulquenberg": "hulkenberg",
    "hulquenberg": "hulkenberg", "hulk": "hulkenberg", "remilton": "hamilton", "hamiltom": "hamilton",
    "lewis": "hamilton", "noris": "norris", "lando": "norris", "piastre": "piastri", "oscar": "piastri",
    "sainz": "sainz", "sains": "sainz", "carlos": "sainz", "estrol": "stroll", "strol": "stroll",
    "gasli": "gasly", "gasle": "gasly", "ocom": "ocon", "loson": "lawson", "adjar": "hadjar", "hadjar": "hadjar",
    "birman": "bearman", "berman": "bearman", "albom": "albon", "lindiblad": "lindblad", "botas": "bottas",
    "perez": "perez", "checo": "perez", "antoneli": "antonelli", "kimi": "antonelli", "fernando": "alonso",
    "bortoleto": "bortoleto", "gabriel": "bortoleto", "colapinto": "colapinto", "franco": "colapinto",
    "tsunoda": "tsunoda", "yuki": "tsunoda", "george": "russell", "charles": "leclerc",
    # como o reconhecimento em inglês costuma escrever
    "le clerc": "leclerc", "leclerk": "leclerc", "hulkenburg": "hulkenberg", "sergio": "perez", "valtteri": "bottas",
    "ollie": "bearman", "oliver": "bearman", "alex": "albon", "isack": "hadjar", "liam": "lawson", "esteban": "ocon",
    "pierre": "gasly", "lance": "stroll", "nico": "hulkenberg", "arvid": "lindblad",
}
NUMEROS = {"primeiro": 1, "segundo": 2, "terceiro": 3, "quarto": 4, "quinto": 5, "sexto": 6, "setimo": 7,
           "oitavo": 8, "nono": 9, "decimo": 10,
           "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
           "eighth": 8, "ninth": 9, "tenth": 10}


def normalizar(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.replace("'", "")                     # what's -> whats, won't -> wont
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\b(engenheiro|engineer|por favor|please|ai|ae|cara|mano|ow|oi|mate|bro)\b", " ", t)
    return " " + re.sub(r"\s+", " ", t).strip() + " "


def tem(t, *palavras):
    return any(f" {p} " in t or (p.endswith("*") and f" {p[:-1]}" in t) for p in palavras)


def _plural(n, um, varios):
    return um if n == 1 else varios


class Conversa:
    def __init__(self, sessao):
        self.s = sessao

    # ---------- quem é o carro de que se fala ----------
    def _carro_citado(self, t):
        s = self.s
        ativos = [c for c in s.carros if c.posicao and c.status_resultado in (2, 3) and c.idx != s.jogador]
        sobrenomes = {}
        for c in ativos:
            n = normalizar(s._nome(c.idx) or c.nome).split()
            if n:
                sobrenomes[n[-1]] = c
        palavras = t.split()
        for i, p in enumerate(palavras):
            alvo = APELIDOS.get(p, p)
            if i + 1 < len(palavras):
                alvo = APELIDOS.get(f"{p} {palavras[i + 1]}", alvo)
            if alvo in sobrenomes:
                return sobrenomes[alvo]
        for p in palavras:
            if len(p) >= 4:
                m = difflib.get_close_matches(p, list(sobrenomes), n=1, cutoff=0.78)
                if m:
                    return sobrenomes[m[0]]
        eu = s.eu
        sem_carro = tem(t, "saindo de frente", "sai de frente", "pneu da frente", "pneus da frente", "asa da frente",
                        "pneu de tras", "pneus de tras", "asa de tras",
                        "front tyre", "front tyres", "front tire", "front tires", "front wing", "front end",
                        "rear tyre", "rear tyres", "rear tire", "rear tires", "rear wing", "rear end")
        if sem_carro:
            return None
        if tem(t, "da frente", "na frente", "a frente", "frente", "ahead", "in front", "car in front"):
            return s._carro_na_posicao(eu.posicao - 1)
        if tem(t, "de tras", "atras", "tras", "behind", "car behind"):
            return s._carro_na_posicao(eu.posicao + 1)
        if tem(t, "lider", "liderando", "primeiro colocado", "leader", "leading", "race leader"):
            return s._carro_na_posicao(1)
        m = re.search(r" p ?(\d{1,2}) ", t)
        if m:
            return s._carro_na_posicao(int(m.group(1)))
        for palavra, n in NUMEROS.items():
            if tem(t, palavra + " lugar", palavra + " colocado", palavra + " place"):
                return s._carro_na_posicao(n)
        return None

    def _nome(self, c):
        return self.s._nome(c.idx) or f"P{c.posicao}"

    # ---------- respostas ----------
    def responder(self, texto):
        t = normalizar(texto)
        s = self.s
        if not t.strip():
            return None
        curta = len(t.split()) <= 4
        if curta and tem(t, "obrigado", "valeu", "brigado", "obrigada", "thanks", "thank you", "cheers"):
            return tr(falas.escolher("Tamo junto. Foco na pista.", "Disponha. Vamos com tudo."),
                      falas.escolher("No worries. Eyes on the road.", "Anytime. Let's go."))
        if curta and tem(t, "bom dia", "boa tarde", "boa noite", "ola", "tudo bem", "hello", "hi", "hey",
                         "good morning", "how are you"):
            return tr(falas.escolher("Tudo certo por aqui. Estou com você.", "Na escuta. Pode falar."),
                      falas.escolher("All good here. I'm with you.", "Copy, go ahead."))

        if tem(t, "saindo de frente", "sai de frente", "subesterc*", "nao vira", "nao entra", "escorrega a frente",
               "saindo de traseira", "sai de traseira", "traseira escapa", "traseira solta", "sobreesterc*", "rodando",
               "escapando", "escapa", "derrapando", "patinando", "acerto", "setup", "regulagem",
               "understeer*", "oversteer*", "wont turn", "doesnt turn", "not turning", "snap*", "loose",
               "sliding", "spinning", "wheelspin", "rear stepping out", "rear end", "front end", "balance") or (
                tem(t, "traseira", "frente", "rear") and tem(t, "entrada", "saida", "meio da curva", "curva", "curvas",
                                                             "entry", "exit", "mid corner", "corner", "corners")
                and not tem(t, "asa", "pneu", "pneus", "carro da frente", "wing", "tyre", "tyres", "tire", "tires")):
            return self._acerto(t)

        vig = getattr(s, "vigia", None)
        if vig is not None and tem(t, "abandon*", "quem saiu", "quem quebrou", "quem bateu", "retire*", "who is out",
                                   "dnf", "quem esta fora", "who crashed"):
            return vig.lista_abandonos()
        if vig is not None and tem(t, "rivais", "rival", "estrategia dos outros", "estrategia deles", "quem precisa parar",
                                   "quem ainda vai parar", "quem ainda precisa parar", "quem vai parar", "rivals",
                                   "rival strategy", "who still has to pit", "who needs to pit", "who has to pit",
                                   "their strategy", "competitors", "concorrentes", "adversarios"):
            return vig.briefing() if s.eh_corrida else tr("A estratégia dos rivais eu acompanho na corrida.",
                                                         "I track rival strategy during the race.")
        carro = self._carro_citado(t)
        if carro is not None and carro.idx != s.jogador:
            return self._sobre_rival(carro, t)
        if tem(t, "safety", "safety car", "bandeira amarela", "carro de seguranca", "vsc", "yellow flag"):
            return self._safety(t)
        if tem(t, "aguenta", "ate o fim", "ate o final", "ate a bandeirada", "chega no fim",
               "make it", "to the end", "until the end", "go the distance", "last until", "last to the end"):
            return self._aguenta()
        if tem(t, "parar", "parada", "paradas", "box", "pit", "estrategia", "undercut", "overcut", "trocar pneu",
               "quando eu paro", "quando paro", "stop", "stops", "strategy", "pit stop", "change tyres", "plan"):
            return s._resp_estrategia()
        if tem(t, "onde estou perdendo", "onde to perdendo", "perdendo tempo", "onde melhorar", "setor", "setores",
               "onde ganho", "onde posso ganhar", "losing time", "sector", "sectors", "improve", "where am i slow"):
            return self._setores()
        if tem(t, "ultrapass*", "overtake", "atacar", "passar ele", "onde passo", "overtaking", "pass him", "attack",
               "where can i pass"):
            return self._ultrapassar()
        if tem(t, "chuva", "chover", "clima", "previsao", "tempo vai", "molhar", "seco",
               "rain", "raining", "weather", "forecast", "wet", "dry"):
            return s._resp_clima()
        if tem(t, "combustivel", "gasolina", "consumo", "tanque", "fuel", "consumption", "tank"):
            return s._resp_combustivel()
        if tem(t, "motor", "pecas", "peca", "turbo", "cambio", "mgu k", "mguk",
               "engine", "parts", "gearbox", "power unit"):
            return s._resp_pecas()
        if tem(t, "dano", "asa", "quebrou", "danificado", "bati", "batida",
               "damage", "damaged", "wing", "broken", "crash", "hit"):
            return self._dano()
        if tem(t, "punicao", "penalidade", "penalizado", "advertencia", "limite de pista", "investigacao",
               "penalty", "penalties", "warning", "warnings", "track limits", "investigation"):
            return self._penalidades()
        if tem(t, "bateria", "ers", "energia", "carga", "battery", "energy", "charge"):
            return self._ers()
        if tem(t, "pneu", "pneus", "desgaste", "temperatura", "borracha", "aquecendo", "esquentando",
               "tyre", "tyres", "tire", "tires", "wear", "temperature", "temperatures", "temps", "overheating"):
            return s._resp_pneus()
        if tem(t, "mais rapido", "volta mais rapida", "melhor volta da corrida", "quem ta voando",
               "fastest", "fastest lap", "quickest", "who is quick*"):
            return self._mais_rapido()
        if tem(t, "minha volta", "ultima volta", "meu tempo", "tempo de volta", "minha melhor", "ritmo", "meu ritmo",
               "my lap", "last lap", "my time", "lap time", "my best", "pace", "my pace"):
            return self._meu_ritmo()
        if tem(t, "quantas voltas", "faltam quantas", "falta quanto", "quanto falta", "tempo restante", "faltam",
               "how many laps", "laps left", "laps to go", "time left", "how long left", "remaining"):
            return self._faltam()
        if tem(t, "posicao", "situacao", "como estou", "como to", "colocacao", "lugar", "como ta", "como esta",
               "position", "situation", "how am i doing", "where am i", "standings", "place", "gaps", "gap"):
            return s._resp_situacao()
        return None

    def _sobre_rival(self, c, t):
        s = self.s
        nome = self._nome(c)
        partes = []
        eu = s.eu
        if not s.eh_corrida:      # treino/classificação: a diferença que importa é a da melhor volta
            if c.melhor_ms and eu.melhor_ms:
                d = (eu.melhor_ms - c.melhor_ms) / 1000
                if abs(d) < 0.0005:
                    rel = tr(f"{nome} está em P{c.posicao}, com o mesmo tempo que você.",
                             f"{nome} is P{c.posicao}, with the same time as you.")
                else:
                    rel = tr(f"{nome} está em P{c.posicao}, {falas.dif(d)} {'mais rápido' if d > 0 else 'mais lento'} que você.",
                             f"{nome} is P{c.posicao}, {falas.dif(d)} {'faster' if d > 0 else 'slower'} than you.")
            else:
                rel = tr(f"{nome} está em P{c.posicao}.", f"{nome} is P{c.posicao}.")
        elif c.posicao < eu.posicao:
            g = s.diferenca(s.jogador, c.idx)
            rel = (tr(f"{nome} está em P{c.posicao}, {falas.gap(g)} à sua frente.",
                      f"{nome} is P{c.posicao}, {falas.gap(g)} ahead of you.") if g
                   else tr(f"{nome} está em P{c.posicao}.", f"{nome} is P{c.posicao}."))
        else:
            g = s.diferenca(c.idx, s.jogador)
            rel = (tr(f"{nome} está em P{c.posicao}, {falas.gap(g)} atrás de você.",
                      f"{nome} is P{c.posicao}, {falas.gap(g)} behind you.") if g
                   else tr(f"{nome} está em P{c.posicao}.", f"{nome} is P{c.posicao}."))
        quer_pneu = tem(t, "pneu", "composto", "parou", "parar", "parada", "box", "pit", "desgaste",
                        "tyre", "tyres", "tire", "tires", "compound", "pitted", "stopped", "stop", "wear")
        quer_ritmo = tem(t, "ritmo", "rapido", "volta", "tempo", "andando", "pace", "fast", "quick", "lap", "lap time")
        quer_gap = tem(t, "quanto", "diferenca", "distancia", "falta", "gap", "longe", "perto", "segundos",
                       "how far", "distance", "far", "close", "seconds", "how much") or not (quer_pneu or quer_ritmo)
        if quer_gap:
            partes.append(rel)
        vig = getattr(s, "vigia", None)
        if (quer_pneu or not quer_ritmo) and vig is not None and s.eh_corrida and not c.pit_status:
            partes.append((tr("Está ", "He is ") if quer_gap else tr(f"{nome} está ", f"{nome} is "))
                          + vig.texto_rival(c, com_nome=False))
        elif quer_pneu or not quer_ritmo:
            pneu = falas_pneu(c.pneu)
            d = max(c.desgaste) if c.desgaste else 0
            n = c.idade_pneu
            txt = tr(f"{'Está' if quer_gap else nome + ' está'} de {pneu} com {n} {_plural(n, 'volta', 'voltas')}",
                     f"{'He is' if quer_gap else nome + ' is'} on the {pneu}, {n} {_plural(n, 'lap', 'laps')} old")
            if d:
                txt += tr(f", {d:.0f} por cento de desgaste", f", {d:.0f} percent wear")
            if c.paradas:
                txt += tr(f", {c.paradas} {_plural(c.paradas, 'parada feita', 'paradas feitas')}.",
                          f", {c.paradas} {_plural(c.paradas, 'stop', 'stops')} made.")
            else:
                txt += tr(", ainda não parou.", ", hasn't stopped yet.")
            if c.pit_status:
                txt = tr(f"{nome} está nos boxes agora. ", f"{nome} is in the pits right now. ") + txt
            partes.append(txt)
        if quer_ritmo:
            if c.ultima_ms and eu.ultima_ms:
                dif = (c.ultima_ms - eu.ultima_ms) / 1000
                if abs(dif) < 0.05:
                    partes.append(tr(f"Última volta {'dele' if quer_gap else 'do ' + nome}: {falas.tempo(c.ultima_ms)}, "
                                     f"igual à sua.",
                                     f"{'His' if quer_gap else nome + chr(39) + 's'} last lap: {falas.tempo(c.ultima_ms)}, "
                                     f"the same as yours."))
                    return " ".join(partes)
                partes.append(tr(f"Última volta {'dele' if quer_gap else 'do ' + nome}: {falas.tempo(c.ultima_ms)}, "
                                 f"{falas.dif(dif)} {'mais lento' if dif > 0 else 'mais rápido'} que você.",
                                 f"{'His' if quer_gap else nome + chr(39) + 's'} last lap: {falas.tempo(c.ultima_ms)}, "
                                 f"{falas.dif(dif)} {'slower' if dif > 0 else 'faster'} than you."))
            elif c.ultima_ms:
                partes.append(tr(f"Última volta dele: {falas.tempo(c.ultima_ms)}.",
                                 f"His last lap: {falas.tempo(c.ultima_ms)}."))
        return " ".join(partes)

    def _aguenta(self):
        s = self.s
        r = s.calcular_plano() if s.eh_corrida else None
        if r:
            melhor, por = r
            sem = por.get(0)
            if sem:
                return tr(f"Aguenta, sim: chega ao fim com cerca de {sem['desg_fim'][0]:.0f} por cento.",
                          f"Yes, they'll make it: about {sem['desg_fim'][0]:.0f} percent at the flag.")
            return tr("Não aguenta até o fim no limite seguro. ",
                      "They won't make it to the end within the safe limit. ") + s._texto_plano(melhor, por)
        return s._resp_pneus()

    def _safety(self, t):
        s = self.s
        if not s.eh_corrida:
            return tr("Safety Car só importa na corrida.", "The Safety Car only matters in the race.")
        r = s.calcular_plano(1)
        if not r:
            return tr("Se entrar Safety Car, normalmente vale parar se faltar mais de um terço da corrida.",
                      "If the Safety Car comes out, it's usually worth stopping with more than a third of the race left.")
        melhor, por = r
        if melhor["paradas"] and melhor["paradas"][0][0] <= 2:
            p = falas_pneu(melhor["paradas"][0][1])
            return tr(f"Se entrar Safety Car agora, pare na hora para o {p}.",
                      f"If the Safety Car comes out now, box straight away for the {p}.")
        return tr("Se entrar Safety Car agora, fique na pista. ",
                  "If the Safety Car comes out now, stay out. ") + s._texto_plano(melhor, por)

    def _setores(self):
        s = self.s
        voltas = [v for v in s.voltas if v.get("valida") and not v.get("teve_pit") and v.get("s1_ms")]
        if len(voltas) < 2:
            return tr("Ainda preciso de mais voltas limpas para comparar os setores.",
                      "I still need more clean laps to compare the sectors.")
        ult = voltas[-1]
        melhores = [min(v[k] for v in voltas if v[k] > 0) for k in ("s1_ms", "s2_ms", "s3_ms")]
        perdas = [(ult[k] - m) / 1000 for k, m in zip(("s1_ms", "s2_ms", "s3_ms"), melhores)]
        pior = max(range(3), key=lambda k: perdas[k])
        txt = tr(f"Na última volta, o setor {pior + 1} foi o que mais perdeu: {falas.dif(perdas[pior])} para o seu melhor.",
                 f"On the last lap, sector {pior + 1} lost the most: {falas.dif(perdas[pior])} off your best.")
        frente = s._carro_na_posicao(s.eu.posicao - 1)
        if frente is not None and frente.ultima_ms and s.eu.ultima_ms and s.eh_corrida:
            dif = (s.eu.ultima_ms - frente.ultima_ms) / 1000
            txt += tr(f" Contra {self._nome(frente)}, a sua volta foi {falas.dif(dif)} "
                      f"{'mais lenta' if dif > 0 else 'mais rápida'}.",
                      f" Against {self._nome(frente)}, your lap was {falas.dif(dif)} "
                      f"{'slower' if dif > 0 else 'faster'}.")
        return txt

    def _ultrapassar(self):
        s = self.s
        txt = tr(f"O melhor ponto é {falas.ultrapassagem(s.pista)}.",
                 f"The best place is {falas.ultrapassagem(s.pista)}.")
        est = getattr(s, "overtake_estado", "")
        if est == "disponivel":
            txt += tr(" O Overtake está disponível agora.", " Overtake is available now.")
        elif est == "ativo":
            txt += tr(" O Overtake está ativo.", " Overtake is active.")
        else:
            txt += tr(" Fique a menos de 1 segundo para ter o Overtake.", " Get within 1 second to have Overtake.")
        return txt

    def _dano(self):
        d = getattr(self.s, "dano", {}) or {}
        partes = []
        nomes = {"asa_dianteira": ("asa dianteira", "front wing"), "asa_traseira": ("asa traseira", "rear wing"),
                 "assoalho": ("assoalho", "floor"), "difusor": ("difusor", "diffuser"),
                 "lateral": ("lateral", "sidepod")}
        for k, (pt, en) in nomes.items():
            if d.get(k):
                partes.append(tr(f"{pt} com {d[k]} por cento", f"{en} {d[k]} percent"))
        if not partes:
            return tr("Nenhum dano no carro.", "No damage on the car.")
        extra = tr(" Vale trocar a asa no box.", " Worth changing the wing at the stop.") \
            if d.get("asa_dianteira", 0) >= 25 else ""
        return tr("Dano: ", "Damage: ") + ", ".join(partes) + "." + extra

    def _penalidades(self):
        s = self.s
        pen, adv = getattr(s, "penalidades_seg", 0), getattr(s, "advertencias", 0)
        if not pen and not adv:
            return tr("Sem penalidades e sem advertências. Continue assim.", "No penalties and no warnings. Keep it up.")
        txt = []
        if pen:
            txt.append(tr(f"Você tem {pen} segundos de penalidade", f"You have a {pen} second penalty"))
        if adv:
            txt.append(tr(f"{adv} {_plural(adv, 'advertência', 'advertências')} por limite de pista",
                          f"{adv} track limits {_plural(adv, 'warning', 'warnings')}"))
        return tr(" e ", " and ").join(txt) + tr(". Cuidado com as zebras.", ". Careful with the kerbs.")

    def _ers(self):
        s = self.s
        pct = round(100 * (getattr(s, "ers", 0) or 0) / 4e6)
        return tr(f"Bateria com {pct} por cento.", f"Battery at {pct} percent.") + (
            tr(" Guarde para atacar na reta.", " Save it to attack on the straight.") if pct < 30 else "")

    def _mais_rapido(self):
        s = self.s
        quem = getattr(s, "dono_volta_rapida", -1)
        melhor = min((c for c in s.carros if c.melhor_ms), key=lambda c: c.melhor_ms, default=None)
        if melhor is None:
            return tr("Ainda ninguém tem volta completa.", "Nobody has a complete lap yet.")
        if quem == s.jogador:
            fim = f": {falas.tempo(s.melhor_ms)}." if s.melhor_ms else "."
            return tr("A volta mais rápida da corrida é sua", "You have the fastest lap of the race") + fim
        if melhor.idx == s.jogador:
            txt = tr(f"Você tem a volta mais rápida: {falas.tempo(melhor.melhor_ms)}.",
                     f"You have the fastest lap: {falas.tempo(melhor.melhor_ms)}.")
        else:
            txt = tr(f"{self._nome(melhor)} tem a volta mais rápida: {falas.tempo(melhor.melhor_ms)}.",
                     f"{self._nome(melhor)} has the fastest lap: {falas.tempo(melhor.melhor_ms)}.")
        if melhor.idx != s.jogador and s.melhor_ms:
            d = falas.dif((s.melhor_ms - melhor.melhor_ms) / 1000)
            txt += tr(f" A sua está {d} atrás.", f" Yours is {d} slower.")
        return txt

    def _meu_ritmo(self):
        s = self.s
        eu = s.eu
        if not eu.ultima_ms:
            return tr("Ainda não tenho volta completa sua.", "I don't have a complete lap from you yet.")
        txt = tr("Última volta: ", "Last lap: ") + f"{falas.tempo(eu.ultima_ms)}."
        if s.melhor_ms and s.melhor_ms != eu.ultima_ms:
            txt += tr(" Sua melhor: ", " Your best: ") + f"{falas.tempo(s.melhor_ms)}."
        frente = s._carro_na_posicao(eu.posicao - 1)
        if s.eh_corrida and frente is not None and frente.ultima_ms:
            dif = (eu.ultima_ms - frente.ultima_ms) / 1000
            txt += tr(f" {self._nome(frente)} fez {falas.dif(dif)} {'mais rápido' if dif > 0 else 'mais devagar'}.",
                      f" {self._nome(frente)} was {falas.dif(dif)} {'faster' if dif > 0 else 'slower'}.")
        return txt

    def _faltam(self):
        s = self.s
        if s.eh_corrida and s.total_voltas:
            f = s.total_voltas - max(0, s.eu.volta - 1)
            return tr(f"Faltam {f} {_plural(f, 'volta', 'voltas')}, contando esta.",
                      f"{f} {_plural(f, 'lap', 'laps')} to go, including this one.")
        if s.tempo_restante:
            m = s.tempo_restante // 60
            return tr(f"Faltam {m} {_plural(m, 'minuto', 'minutos')} de sessão.",
                      f"{m} {_plural(m, 'minute', 'minutes')} left in the session.")
        return tr("Não tenho essa informação agora.", "I don't have that information right now.")

    def _acerto(self, t):
        entrada = tem(t, "entrada", "freada", "freio", "frear", "entry", "braking", "brake", "turn in")
        saida = tem(t, "saida", "acelerando", "aceleracao", "tracao", "acelero", "exit", "throttle", "traction",
                    "wheelspin", "accelerating")
        frente = tem(t, "frente", "subesterc*", "nao vira", "nao entra", "understeer*", "wont turn", "doesnt turn",
                     "not turning", "front end", "front")
        traseira = tem(t, "traseira", "sobreesterc*", "rodando", "escapa", "escapando", "solta", "derrapando",
                       "patinando", "oversteer*", "rear", "rear end", "loose", "snap*", "spinning", "sliding",
                       "wheelspin", "rear stepping out")
        if frente and entrada:
            return tr("Saindo de frente na entrada: balanço de freio um ponto para trás e diferencial na desaceleração "
                      "5 pontos mais baixo. Se não resolver, asa dianteira mais 2.",
                      "Understeer on entry: brake bias one click rearward and off-throttle differential "
                      "5 points lower. If that doesn't fix it, front wing plus 2.")
        if frente and saida:
            return tr("Saindo de frente na saída: diferencial na aceleração 5 pontos mais baixo e barra dianteira 1 mais macia.",
                      "Understeer on exit: on-throttle differential 5 points lower and front anti-roll bar 1 softer.")
        if frente:
            return tr("Saindo de frente no meio da curva: asa dianteira mais 2 e barra estabilizadora dianteira 1 a 2 mais macia.",
                      "Mid-corner understeer: front wing plus 2 and front anti-roll bar 1 to 2 softer.")
        if traseira and entrada:
            return tr("Traseira escapando na entrada: diferencial na desaceleração 5 pontos mais alto e balanço de freio "
                      "um ponto para frente.",
                      "Rear stepping out on entry: off-throttle differential 5 points higher and brake bias "
                      "one click forward.")
        if traseira and saida:
            return tr("Traseira escapando na saída: diferencial na aceleração 5 pontos mais baixo e acelerador mais "
                      "progressivo. Se precisar, barra traseira 1 mais macia.",
                      "Oversteer on exit: on-throttle differential 5 points lower and a smoother throttle. "
                      "If needed, rear anti-roll bar 1 softer.")
        if traseira:
            return tr("Traseira solta no meio da curva: asa traseira mais 2 e barra estabilizadora traseira 1 mais macia.",
                      "Loose rear mid-corner: rear wing plus 2 and rear anti-roll bar 1 softer.")
        return tr("Me diz o que o carro está fazendo: saindo de frente ou de traseira, e se é na entrada, "
                  "no meio ou na saída da curva.",
                  "Tell me what the car is doing: understeer or oversteer, and whether it's on entry, "
                  "mid-corner or on exit.")


def falas_pneu(comp):
    pt = {16: "macio", 17: "médio", 18: "duro", 7: "intermediário", 8: "pneu de chuva",
          19: "supermacio", 20: "macio", 21: "médio", 22: "duro"}
    en = {16: "soft", 17: "medium", 18: "hard", 7: "intermediate", 8: "full wet",
          19: "supersoft", 20: "soft", 21: "medium", 22: "hard"}
    return tr(pt.get(comp, "pneu"), en.get(comp, "tyre"))
