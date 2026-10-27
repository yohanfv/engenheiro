# -*- coding: utf-8 -*-
"""
Vigia da pista (só na corrida): o que acontece com os OUTROS carros.

- Abandonos: quem, onde (curva oficial e setor) e o motivo (falha mecânica, dano, toque com alguém...).
- Toques entre carros perto de você, carro parado ou muito lento na pista, dano na asa de um rival.
- Piloto mais lento que o normal: perdeu tempo numa volta (e em qual setor).
- Estratégia dos rivais: pneu, idade, desgaste e ritmo de desgaste de cada um, quando devem parar,
  quem ainda precisa trocar de composto, chance/ameaça de undercut e overcut.
"""

import statistics
import time
import unicodedata

import falas
from idioma import L as tr

SECOS = (16, 17, 18)
LIMITE_PARADA = 70.0          # desgaste (%) em que a IA costuma parar

# motivo do evento RTMT -> (português, inglês); os outros motivos (terminou, sessão simulada...) não são abandono
MOTIVOS = {1: None, 3: ("dano no carro", "terminal damage"), 4: ("carro parado", "car stopped"),
           6: ("bandeira preta", "black flag"), 8: ("falha mecânica", "mechanical failure")}
NAO_E_ABANDONO = {2, 5, 7, 9, 10}


def _norm(t):
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return "".join(ch for ch in t if unicodedata.category(ch) != "Mn").strip()


def _pneu(comp):
    pt = {16: "macio", 17: "médio", 18: "duro", 7: "intermediário", 8: "pneu de chuva", 19: "supermacio",
          20: "macio", 21: "médio", 22: "duro"}
    en = {16: "soft", 17: "medium", 18: "hard", 7: "intermediate", 8: "full wet", 19: "supersoft",
          20: "soft", 21: "medium", 22: "hard"}
    return tr(pt.get(comp, "pneu"), en.get(comp, "tyre"))


class Vigia:
    def __init__(self, sessao, curvas_oficiais):
        self.s = sessao
        self._curvas = curvas_oficiais or {}    # pista -> [["1", 0.067], ...] fração da volta de cada curva
        self.anunciados = set()                 # abandonos já falados
        self.correu = set()                     # carros vistos correndo (para não "abandonar" quem nem largou)
        self.pendente = {}                      # idx -> instante em que o status virou abandono (espera o RTMT)
        self.lento_desde = {}
        self.lento_avisado = set()
        self.voltas = {}                        # idx -> [(ms, s1, s2, s3)] voltas limpas
        self.stints = {}                        # idx -> {"chave": (paradas, comp), "comp", "pontos": [(volta, desg)]}
        self.compostos = {}                     # idx -> compostos usados
        self.colisoes = {}                      # idx -> (instante, outro idx)
        self.asa_avisada = {}
        self.undercut_avisado = set()
        self.ultimo_briefing = 0
        self._ult_tick = 0.0
        self.pos_correndo = {}                  # idx -> última posição andando normalmente

    # ------------------------------------------------------------------ utilidades
    @property
    def ativo(self):
        return self.s.eh_corrida

    def _corrida_andando(self):
        s = self.s
        luzes = getattr(s, "_t_luzes", None)
        if luzes is not None:
            return time.monotonic() - luzes > 20
        return s.eu.volta >= 2

    def nome(self, idx):
        return self.s._nome(idx) or tr(f"o carro {idx + 1}", f"car {idx + 1}")

    @property
    def curvas(self):
        return self._curvas.get(self.s.pista) or []

    def curva(self, dist):
        comp = self.s.comprimento_pista
        if not self.curvas or comp <= 0 or dist < 0:
            return None
        def d(f):
            x = abs(f * comp - dist)
            return min(x, comp - x)
        return min(self.curvas, key=lambda c: d(c[1]))[0]

    def onde(self, c):
        if c.pit_status:
            return tr("nos boxes", "in the pits")
        n = self.curva(c.dist_volta)
        setor = getattr(c, "setor", -1) + 1
        if n and setor >= 1:
            return tr(f"na curva {n}, setor {setor}", f"at turn {n}, sector {setor}")
        if n:
            return tr(f"na curva {n}", f"at turn {n}")
        return tr(f"no setor {setor}", f"in sector {setor}") if setor >= 1 else ""

    def _a_frente_na_pista(self, c, ate_m):
        """O carro está na pista à sua frente, a menos de 'ate_m' metros (você vai chegar nele)?"""
        comp, eu = self.s.comprimento_pista, self.s.eu
        if comp <= 0 or c.dist_volta < 0 or eu.dist_volta < 0:
            return False
        return 0 < (c.dist_volta - eu.dist_volta) % comp < ate_m

    def rivais_cfg(self):
        txt = self.s.cfg.get("rivais") or ""
        return [_norm(x) for x in str(txt).replace(";", ",").split(",") if _norm(x)]

    def eh_rival(self, c):
        """Rival declarado no config, ou o companheiro de equipe."""
        s = self.s
        if c.idx == s.jogador:
            return False
        if c.equipe not in (-1, None) and c.equipe == s.eu.equipe:
            mesma = [x for x in s.carros if x.equipe == c.equipe and x.idx != s.jogador and x.posicao]
            if len(mesma) == 1:          # o companheiro de equipe (se a equipe tiver um só outro carro)
                return True
        nome = _norm(s._nome(c.idx))
        return any(r and (r in nome or nome.endswith(r)) for r in self.rivais_cfg())

    def relevante(self, c, perto=3):
        eu = self.s.eu
        return bool(eu.posicao and c.posicao and abs(c.posicao - eu.posicao) <= perto) or self.eh_rival(c)

    def _falar(self, txt, prio, chave, intervalo=9999):
        self.s.falar(txt, prio, chave, intervalo)

    # ------------------------------------------------------------------ eventos do jogo
    def abandono(self, idx, motivo=0):
        s = self.s
        if not self.ativo or idx == s.jogador or idx in self.anunciados or not (0 <= idx < len(s.carros)):
            return
        if motivo in NAO_E_ABANDONO or not s.av.get("abandonos_e_incidentes", True):
            return
        self.anunciados.add(idx)
        self.pendente.pop(idx, None)
        c = s.carros[idx]
        nome = self.nome(idx)
        quando, outro = self.colisoes.get(idx, (0, None))
        par = MOTIVOS.get(motivo)
        if outro is not None and time.monotonic() - quando < 120:
            motivo_txt = tr(f"depois do toque com {self.nome(outro)}", f"after contact with {self.nome(outro)}")
        elif par:
            motivo_txt = tr(*par)
        else:
            motivo_txt = ""
        onde = self.onde(c)
        p = self.pos_correndo.get(idx) or c.posicao
        pos = f"P{p}" if p else ""
        txt = tr(f"Abandono! {nome}{', que estava em ' + pos if pos else ''}, parou {onde}.",
                 f"Retirement! {nome}{', running ' + pos if pos else ''}, has stopped {onde}.")
        if motivo_txt:
            txt += tr(f" Motivo: {motivo_txt}.", f" Reason: {motivo_txt}.")
        na_pista = not c.pit_status
        if na_pista and s.safety_car == 0:
            if self._a_frente_na_pista(c, 2500):
                txt += tr(" Ele está à sua frente: cuidado, bandeira amarela.",
                          " He is ahead of you on track: careful, yellow flag.")
            else:
                txt += tr(" Pode ter bandeira amarela ou Safety Car.", " There could be a yellow flag or a Safety Car.")
        self._falar(txt, 2 if na_pista else 1, f"abandono-{idx}")
        s.evento(tr(f"Abandono: {nome} {onde}" + (f" ({motivo_txt})" if motivo_txt else ""),
                    f"Retirement: {nome} {onde}" + (f" ({motivo_txt})" if motivo_txt else "")))

    def colisao(self, i1, i2):
        s = self.s
        if not self.ativo:
            return
        agora = time.monotonic()
        for a, b in ((i1, i2), (i2, i1)):
            if 0 <= a < len(s.carros):
                self.colisoes[a] = (agora, b)
        if s.jogador in (i1, i2) or not s.av.get("abandonos_e_incidentes", True) or not self._corrida_andando():
            return
        if not (0 <= i1 < len(s.carros) and 0 <= i2 < len(s.carros)):
            return
        c1, c2 = s.carros[i1], s.carros[i2]
        if not (self.relevante(c1, 4) or self.relevante(c2, 4) or self._a_frente_na_pista(c1, 2000)):
            return
        onde = "" if c1.pit_status else " " + self.onde(c1)
        txt = tr(f"Toque entre {self.nome(i1)} e {self.nome(i2)}{onde}.",
                 f"Contact between {self.nome(i1)} and {self.nome(i2)}{onde}.")
        if not c1.pit_status and self._a_frente_na_pista(c1, 2000):
            txt += tr(" Fica à sua frente: cuidado com detritos.", " It's ahead of you: watch for debris.")
        self._falar(txt, 1, f"coll-{min(i1, i2)}-{max(i1, i2)}", 30)
        s.evento(tr(f"Toque: {self.nome(i1)} x {self.nome(i2)}", f"Contact: {self.nome(i1)} x {self.nome(i2)}"))

    def dano_asa(self, idx, asa):
        s = self.s
        if not self.ativo or idx == s.jogador or not s.av.get("abandonos_e_incidentes", True):
            return
        if asa < 30:
            if asa < 10:
                self.asa_avisada.pop(idx, None)
            return
        if asa < self.asa_avisada.get(idx, 0) + 20 or not self.relevante(s.carros[idx], 3):
            return
        self.asa_avisada[idx] = asa
        nome = self.nome(idx)
        self._falar(tr(f"{nome} está com a asa dianteira danificada, {asa} por cento. Vai perder ritmo e pode "
                       f"parar para trocar.",
                       f"{nome} has front wing damage, {asa} percent. He will lose pace and may pit for a new wing."),
                    1, f"asa-riv-{idx}", 60)
        s.evento(tr(f"{nome}: dano na asa {asa}%", f"{nome}: wing damage {asa}%"))

    # ------------------------------------------------------------------ a cada pacote de voltas
    def tick(self):
        s = self.s
        if not self.ativo:
            return
        agora = float(getattr(s, "tempo_sessao", 0) or 0) or time.monotonic()
        if 0 <= agora - self._ult_tick < 0.4:
            return
        self._ult_tick = agora
        andando = self._corrida_andando()
        for c in s.carros:
            if c.idx == s.jogador or not c.posicao:
                continue
            st = c.status_resultado
            if st == 2:
                self.correu.add(c.idx)
                if getattr(c, "vel", None) is None or c.vel >= 60 or c.pit_status:
                    self.pos_correndo[c.idx] = c.posicao
            elif st in (4, 6, 7) and c.idx in self.correu and c.idx not in self.anunciados:
                # abandonou e o jogo não mandou o evento (ou ainda vai mandar): espera um pouco
                t0 = self.pendente.setdefault(c.idx, agora)
                if agora - t0 > 3:
                    self.abandono(c.idx, 8 if st == 7 else (6 if st == 5 else 0))
            if not andando or st != 2 or c.pit_status or s.safety_car or not s.av.get("carros_lentos", True):
                self.lento_desde.pop(c.idx, None)
                continue
            vel = getattr(c, "vel", None)
            if vel is None:
                continue
            if vel < 60:
                t0 = self.lento_desde.setdefault(c.idx, agora)
                if agora - t0 > 2.5 and c.idx not in self.lento_avisado:
                    self.lento_avisado.add(c.idx)
                    nome = self.nome(c.idx)
                    frente = self._a_frente_na_pista(c, 2500)
                    txt = (tr("Cuidado! Carro lento à sua frente: ", "Careful! Slow car ahead of you: ") if frente
                           else tr("Carro lento na pista: ", "Slow car on track: "))
                    txt += f"{nome}, {self.onde(c)}."
                    self._falar(txt, 2 if frente else 1, f"lento-{c.idx}", 60)
                    s.evento(tr(f"Carro lento: {nome} {self.onde(c)}", f"Slow car: {nome} {self.onde(c)}"))
            elif vel > 120:
                self.lento_desde.pop(c.idx, None)
                if c.idx in self.lento_avisado and c.idx not in self.anunciados:
                    self.lento_avisado.discard(c.idx)

    # ------------------------------------------------------------------ fim de volta de outro carro
    def volta_carro(self, c, ms, s1, s2, s3):
        s = self.s
        if not self.ativo or c.idx == s.jogador:
            return
        volta = c.volta                     # volta que acabou de terminar
        comp = c.pneu
        if comp:
            self.compostos.setdefault(c.idx, set()).add(comp)
        # stint e desgaste
        chave = (c.paradas, comp)
        st = self.stints.get(c.idx)
        if st is None or st["chave"] != chave:
            st = self.stints[c.idx] = {"chave": chave, "comp": comp, "pontos": []}
        if not c.teve_pit and c.desgaste:
            st["pontos"].append((volta, max(c.desgaste)))
        # volta mais lenta que o normal
        limpa = (not c.teve_pit and c.ultima_valida and s.safety_car == 0 and volta > 1 and s1 and s2 and s3 > 0
                 and s.clima < 3)
        if not limpa:
            return
        hist = self.voltas.setdefault(c.idx, [])
        anteriores = hist[-4:]
        hist.append((ms, s1, s2, s3))
        if len(anteriores) < 2 or not s.av.get("carros_lentos", True) or not self.relevante(c, 3):
            return
        med = statistics.median(v[0] for v in anteriores)
        perda = ms - med
        if perda < max(2000, med * 0.015):
            return
        setores = [s1, s2, s3]
        perdas = [setores[k] - statistics.median(v[k + 1] for v in anteriores) for k in range(3)]
        k = max(range(3), key=lambda j: perdas[j])
        nome = self.nome(c.idx)
        lado = (tr("na sua frente", "ahead of you") if c.posicao < s.eu.posicao else tr("atrás de você", "behind you"))
        self._falar(tr(f"{nome}, {lado}, perdeu {falas.dif(perda / 1000)} nesta volta, a maior parte no setor {k + 1}. "
                       f"Pode estar com problema.",
                       f"{nome}, {lado}, lost {falas.dif(perda / 1000)} on that lap, mostly in sector {k + 1}. "
                       f"He may have a problem."),
                    1, f"lento-volta-{c.idx}", 150)
        s.evento(tr(f"{nome} perdeu {perda / 1000:.1f}s (setor {k + 1})", f"{nome} lost {perda / 1000:.1f}s (sector {k + 1})"))

    # ------------------------------------------------------------------ estratégia dos rivais
    def taxa(self, c):
        st = self.stints.get(c.idx)
        pts = (st or {}).get("pontos") or []
        if st and st["comp"] != c.pneu:
            pts = []
        if len(pts) >= 2 and pts[-1][0] > pts[0][0]:
            t = (pts[-1][1] - pts[0][1]) / (pts[-1][0] - pts[0][0])
            if t > 0.3:
                return t
        if c.idade_pneu >= 2 and c.desgaste and max(c.desgaste) > 0:
            return max(c.desgaste) / c.idade_pneu
        return None

    def previsao(self, c):
        s = self.s
        total = s.total_voltas or 0
        desg = max(c.desgaste) if c.desgaste else 0
        taxa = self.taxa(c)
        usados = {x for x in self.compostos.get(c.idx, set()) | {c.pneu} if x in SECOS}
        chuva = s.clima >= 3 or c.pneu not in SECOS
        precisa_trocar = bool(total and not chuva and len(usados) < 2)
        volta_prev = None
        if taxa:
            volta_prev = max(c.volta, c.volta + round((LIMITE_PARADA - desg) / taxa) - 1)
        aguenta = bool(total and volta_prev is not None and volta_prev >= total)
        if aguenta:
            volta_prev = None
        return {"desg": desg, "taxa": taxa, "volta": volta_prev, "precisa_trocar": precisa_trocar,
                "aguenta": aguenta, "total": total, "chuva": chuva}

    def situacao_rival(self, c):
        """Só a parte da estratégia: 'deve parar por volta da volta 12', 'vai até o fim'..."""
        s = self.s
        p = self.previsao(c)
        if not (p["total"] and s.eh_corrida):
            return ""
        if p["volta"] is not None:
            txt = tr(f"deve parar por volta da volta {p['volta']}", f"should pit around lap {p['volta']}")
            depois = p["total"] - p["volta"]
            if p["taxa"] and depois * p["taxa"] * 0.85 > LIMITE_PARADA:
                txt += tr(" e talvez pare mais uma vez", " and may stop once more")
            return txt
        if p["precisa_trocar"]:
            return tr("ainda precisa trocar de composto, então vai parar mais para o fim",
                      "still has to use another compound, so he will pit later on")
        if p["aguenta"] or c.paradas:
            return tr("deve ir até o fim sem parar", "should go to the end without stopping")
        return ""

    def texto_rival(self, c, com_nome=True):
        p = self.previsao(c)
        idade = c.idade_pneu
        if com_nome:
            txt = tr(f"{self.nome(c.idx)}, P{c.posicao}, de {_pneu(c.pneu)} com {idade} {'volta' if idade == 1 else 'voltas'}",
                     f"{self.nome(c.idx)}, P{c.posicao}, on {_pneu(c.pneu)}s, {idade} {'lap' if idade == 1 else 'laps'} old")
        else:
            txt = tr(f"de {_pneu(c.pneu)} com {idade} {'volta' if idade == 1 else 'voltas'}",
                     f"on the {_pneu(c.pneu)}, {idade} {'lap' if idade == 1 else 'laps'} old")
        if p["desg"] >= 1:
            txt += f" ({p['desg']:.0f}%)"
        if c.paradas:
            txt += tr(f", já parou {c.paradas} {'vez' if c.paradas == 1 else 'vezes'}",
                      f", {c.paradas} {'stop' if c.paradas == 1 else 'stops'} done")
        sit = self.situacao_rival(c)
        return txt + (": " + sit if sit else "") + "."

    def lista_abandonos(self):
        s = self.s
        if not self.anunciados:
            return tr("Nenhum abandono até agora.", "No retirements so far.")
        nomes = ", ".join(self.nome(i) for i in sorted(self.anunciados))
        n = len(self.anunciados)
        return tr(f"{n} {'abandono' if n == 1 else 'abandonos'} até agora: {nomes}.",
                  f"{n} {'retirement' if n == 1 else 'retirements'} so far: {nomes}.")

    def escolher_carros(self):
        """Os carros que você está disputando (2 à frente e 2 atrás, perto) e os rivais declarados."""
        s = self.s
        eu = s.eu
        lista = []
        for d in (-1, -2, 1, 2):
            c = s._carro_na_posicao(eu.posicao + d)
            if c is None or c.status_resultado != 2:
                continue
            g = s.diferenca(s.jogador, c.idx) if d < 0 else s.diferenca(c.idx, s.jogador)
            if abs(d) == 1 or (g is not None and g < 8):
                lista.append(c)
        for c in s.carros:
            if c not in lista and c.posicao and c.status_resultado == 2 and self.eh_rival(c):
                lista.append(c)
        return sorted(lista, key=lambda c: c.posicao)

    def meu_plano(self, feitas=None):
        s = self.s
        feitas = max(0, s.eu.volta - 1) if feitas is None else feitas
        try:
            r = s.calcular_plano(feitas=feitas)
        except Exception:  # noqa: BLE001
            r = None
        if not r or not r[0]["paradas"]:
            return None, r
        return feitas + r[0]["paradas"][0][0], r

    def briefing(self, feitas=None):
        s = self.s
        carros = self.escolher_carros()
        if not carros:
            return tr("Ainda não tenho rivais perto para analisar.", "No rivals close enough to analyse yet.")
        partes = [tr("Estratégia dos rivais.", "Rival strategy.")]
        for c in carros[:4]:
            partes.append(self.texto_rival(c))
        minha, _ = self.meu_plano(feitas)
        if minha:
            partes.append(tr(f"Nosso plano: parar na volta {minha}.", f"Our plan: pit on lap {minha}."))
        return " ".join(partes)

    def fim_volta_jogador(self):
        """Chamado quando você completa uma volta: briefing de estratégia e chances de undercut."""
        s = self.s
        if not self.ativo or not s.av.get("estrategia_rivais", True) or s.clima >= 3 or not s.total_voltas:
            return
        eu = s.eu
        feitas = eu.volta                    # a volta que acabou de terminar ainda é a "atual" aqui
        if feitas < 3 or feitas >= s.total_voltas - 1:
            return
        if eu.teve_pit or getattr(s, "_pit_status", 0):    # volta de box: posições embaralhadas, fica para a próxima
            return
        minha, _ = self.meu_plano(feitas)
        # briefing: na volta 3 e depois a cada 6 voltas, ou quando a nossa parada está perto
        perto_da_parada = minha is not None and 0 <= minha - feitas <= 2
        if feitas == 3 or feitas - self.ultimo_briefing >= 6 or (perto_da_parada and feitas - self.ultimo_briefing >= 3):
            self.ultimo_briefing = feitas
            self._falar(self.briefing(feitas), 1, f"briefing-{feitas}")
        # undercut no carro da frente
        if minha is None or not (0 <= minha - feitas <= 2):
            return
        frente = s._carro_na_posicao(eu.posicao - 1)
        if frente is None or frente.status_resultado != 2 or frente.idx in self.undercut_avisado:
            return
        g = s.diferenca(s.jogador, frente.idx)
        p = self.previsao(frente)
        tarde = ((p["volta"] is not None and p["volta"] >= minha + 2) or (p["volta"] is None and p["precisa_trocar"]))
        if g is not None and g < 2.5 and tarde:
            self.undercut_avisado.add(frente.idx)
            nome = self.nome(frente.idx)
            quando = (tr(f"só deve parar por volta da volta {p['volta']}", f"should only pit around lap {p['volta']}")
                      if p["volta"] is not None else tr("deve esticar o stint dele", "is likely to run long"))
            self._falar(tr(f"Chance de undercut no {nome}: ele está a {falas.gap(g)} e {quando}. "
                           f"Se pararmos antes e fizermos boas voltas de saída, passamos ele.",
                           f"Undercut chance on {nome}: he is {falas.gap(g)} ahead and {quando}. "
                           f"If we pit first and nail the out lap, we jump him."),
                        2, f"undercut-{frente.idx}")

    def rival_entrou_box(self, c, atras):
        """Um carro colado em você entrou nos boxes: cobrir o undercut ou tentar o overcut."""
        s = self.s
        if not self.ativo or not s.av.get("estrategia_rivais", True) or s.clima >= 3:
            return
        eu = s.eu
        feitas = max(0, eu.volta - 1)
        minha, _ = self.meu_plano()
        g = s.diferenca(c.idx, s.jogador) if atras else s.diferenca(s.jogador, c.idx)
        if g is None or g > 3.5:
            return
        nome = self.nome(c.idx)
        if atras and minha is not None and minha - feitas <= 4:
            self._falar(tr(f"{nome} está tentando o undercut. Box na próxima volta para cobrir.",
                           f"{nome} is going for the undercut. Box next lap to cover him."), 2, f"cobrir-{c.idx}", 120)
        elif atras:
            self._falar(tr(f"{nome} parou cedo. Nosso pneu aguenta: força nas próximas voltas para abrir vantagem.",
                           f"{nome} pitted early. Our tyres are fine: push now to build a gap."), 1, f"cobrir-{c.idx}", 120)
        elif minha is None or minha - feitas >= 2:
            self._falar(tr(f"{nome} parou. Pista livre: força o ritmo agora para tentar o overcut.",
                           f"{nome} has pitted. Clear air: push now to try the overcut."), 1, f"overcut-{c.idx}", 120)
