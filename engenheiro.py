# -*- coding: utf-8 -*-
"""
Engenheiro de corrida para o F1 25 (PS5 / PC / Xbox).

- Recebe a telemetria UDP que o jogo envia (porta 20777 por padrão).
- Fala avisos em português pelo alto-falante do computador (voz do Windows).
- Grava tudo em arquivos CSV por sessão, para análise depois.
- Repassa os dados para o SimHub (porta 20778), para os dois funcionarem juntos.

Uso:
    python engenheiro.py               -> modo normal
    python engenheiro.py --testar-voz  -> só testa a voz e sai
    python engenheiro.py --ouvir-vozes -> toca as vozes disponíveis para você escolher
    python engenheiro.py --sem-voz     -> roda sem falar (só mostra na tela)
"""

import csv
from collections import deque
import heapq
import itertools
import json
import os
import socket
import statistics
import sys
import threading
import bisect
import time
from datetime import datetime

AQUI = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
if not getattr(sys, "frozen", False):      # no executável quem escolhe de onde vem o código é o app.py
    sys.path.insert(0, AQUI)
if __name__ == "__main__":
    # rodando como "py engenheiro.py": quem fizer "import engenheiro" (painel, simulador) recebe ESTE módulo,
    # não uma segunda cópia (senão o botão Fechar do painel não fecha o programa)
    sys.modules.setdefault("engenheiro", sys.modules[__name__])

import falas  # noqa: E402
import vigia  # noqa: E402
import idioma  # noqa: E402
from idioma import L as tr, Bi, BiLista  # noqa: E402

from f1_types import (PacketHeader, PacketSessionData, PacketLapData, PacketMotionData,  # noqa: E402
                      PacketEventData, PacketParticipantsData, PacketCarSetupData,
                      PacketCarTelemetryData, PacketCarStatusData, PacketCarDamageData)
try:
    from f1_types import PacketCarTelemetry2Data  # noqa: E402  (só existe no formato 2026)
except ImportError:  # pragma: no cover
    PacketCarTelemetry2Data = None

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# --------------------------------------------------------------------------------------
# Tabelas e utilitários
# --------------------------------------------------------------------------------------

PISTAS = Bi({
    0: "Melbourne", 1: "Paul Ricard", 2: ("Xangai", "Shanghai"), 3: ("Bahrein", "Bahrain"), 4: "Barcelona",
    5: ("Mônaco", "Monaco"), 6: ("Canadá", "Canada"), 7: "Silverstone", 8: "Hockenheim", 9: ("Hungria", "Hungary"),
    10: "Spa", 11: "Monza", 12: ("Singapura", "Singapore"), 13: "Suzuka", 14: "Abu Dhabi",
    15: "Austin", 16: "Interlagos", 17: ("Áustria", "Austria"), 18: "Sochi", 19: ("México", "Mexico"),
    20: "Baku", 21: ("Bahrein curto", "Bahrain short"), 22: ("Silverstone curto", "Silverstone short"),
    23: ("Austin curto", "Austin short"), 24: ("Suzuka curto", "Suzuka short"), 25: ("Hanói", "Hanoi"),
    26: "Zandvoort", 27: ("Ímola", "Imola"), 28: "Portimão", 29: "Jeddah", 30: "Miami", 31: "Las Vegas",
    32: ("Catar", "Qatar"), 39: ("Silverstone invertido", "Silverstone reverse"),
    40: ("Áustria invertida", "Austria reverse"), 41: ("Zandvoort invertido", "Zandvoort reverse"),
    42: ("Madri", "Madrid"),
})

SESSOES = Bi({
    0: ("Sessão", "Session"), 1: ("Treino Livre 1", "Practice 1"), 2: ("Treino Livre 2", "Practice 2"),
    3: ("Treino Livre 3", "Practice 3"), 4: ("Treino curto", "Short practice"), 5: ("Classificação 1", "Qualifying 1"),
    6: ("Classificação 2", "Qualifying 2"), 7: ("Classificação 3", "Qualifying 3"),
    8: ("Classificação curta", "Short qualifying"), 9: ("Classificação de volta única", "One-shot qualifying"),
    10: ("Classificação da Sprint 1", "Sprint Shootout 1"), 11: ("Classificação da Sprint 2", "Sprint Shootout 2"),
    12: ("Classificação da Sprint 3", "Sprint Shootout 3"), 13: ("Classificação da Sprint curta", "Short Sprint Shootout"),
    14: ("Classificação da Sprint de volta única", "One-shot Sprint Shootout"), 15: ("Corrida", "Race"),
    16: ("Corrida 2", "Race 2"), 17: ("Corrida 3", "Race 3"), 18: ("Contrarrelógio", "Time Trial"),
})
SESSOES_TREINO = {1, 2, 3, 4}
SESSOES_CLASSIF = {5, 6, 7, 8, 9, 10, 11, 12, 13, 14}
SESSOES_CORRIDA = {15, 16, 17}
CORTE_Q1 = {5, 10}
CORTE_Q2 = {6, 11}

CLIMA = Bi({0: ("céu limpo", "clear"), 1: ("poucas nuvens", "light cloud"), 2: ("nublado", "overcast"),
            3: ("chuva fraca", "light rain"), 4: ("chuva forte", "heavy rain"), 5: ("tempestade", "storm"),
            6: ("tempestade", "storm")})

PNEU_VISUAL = Bi({16: ("macio", "soft"), 17: ("médio", "medium"), 18: ("duro", "hard"), 7: ("intermediário", "intermediate"),
                  8: ("chuva", "wet"), 19: ("supermacio", "supersoft"), 20: ("macio", "soft"), 21: ("médio", "medium"),
                  22: ("duro", "hard"), 15: ("chuva", "wet")})
PNEU_PLURAL = Bi({16: ("macios", "softs"), 17: ("médios", "mediums"), 18: ("duros", "hards"),
                  7: ("intermediários", "intermediates"), 8: ("de chuva", "wets"), 20: ("macios", "softs"),
                  21: ("médios", "mediums"), 22: ("duros", "hards"), 15: ("de chuva", "wets"),
                  19: ("supermacios", "supersofts")})
PNEUS_SECOS = {16, 17, 18, 19, 20, 21, 22}
PNEUS_CHUVA = {7, 8, 15}

# Equipes de 2026: nome e cor oficial (a mesma das transmissões e da cronometragem da F1).
EQUIPES = {
    "mclaren": ("McLaren", "#F47600"), "ferrari": ("Ferrari", "#ED1131"), "redbull": ("Red Bull", "#4781D7"),
    "mercedes": ("Mercedes", "#00D7B6"), "aston": ("Aston Martin", "#229971"), "williams": ("Williams", "#1868DB"),
    "rb": ("Racing Bulls", "#6C98FF"), "haas": ("Haas", "#B6BABD"), "audi": ("Audi", "#F50537"),
    "alpine": ("Alpine", "#00A1E8"), "cadillac": ("Cadillac", "#6E7378"),
}
# Piloto -> equipe (grid de 2026 e reservas). Só é usado quando o jogo não diz a equipe.
PILOTO_EQUIPE = {
    "norris": "mclaren", "piastri": "mclaren", "leclerc": "ferrari", "hamilton": "ferrari",
    "verstappen": "redbull", "hadjar": "redbull", "russell": "mercedes", "antonelli": "mercedes",
    "alonso": "aston", "stroll": "aston", "albon": "williams", "sainz": "williams",
    "lawson": "rb", "lindblad": "rb", "ocon": "haas", "bearman": "haas",
    "hulkenberg": "audi", "hülkenberg": "audi", "bortoleto": "audi", "gasly": "alpine", "colapinto": "alpine",
    "bottas": "cadillac", "perez": "cadillac", "pérez": "cadillac",
    "tsunoda": "redbull", "doohan": "alpine", "drugovich": "aston", "herta": "cadillac", "iwasa": "rb",
}
# Id da equipe que o jogo manda -> equipe. Vale mais que o nome: no modo carreira os pilotos trocam de equipe.
ID_EQUIPE = {
    # carros de 2026 (pacote da temporada 2026)
    476: "mercedes", 477: "ferrari", 478: "redbull", 479: "williams", 480: "aston", 481: "alpine", 482: "rb",
    483: "haas", 484: "mclaren", 485: "audi", 486: "cadillac",
    # carros de 2025 e 2024
    0: "mercedes", 1: "ferrari", 2: "redbull", 3: "williams", 4: "aston", 5: "alpine", 6: "rb",
    7: "haas", 8: "mclaren", 9: "audi",
    185: "mercedes", 186: "ferrari", 187: "redbull", 188: "williams", 189: "aston", 190: "alpine", 191: "rb",
    192: "haas", 193: "mclaren", 194: "audi",
}


def equipe_do_nome(nome):
    p = str(nome or "").strip().lower().split()
    for parte in reversed(p):
        if parte in PILOTO_EQUIPE:
            return PILOTO_EQUIPE[parte]
    return None


def cor_equipe(eq):
    """Compatibilidade: cor pela id do jogo."""
    chave = ID_EQUIPE.get(eq)
    return EQUIPES[chave][1] if chave else "#888888"


# Ordem das rodas nos arrays do jogo: traseira esq., traseira dir., dianteira esq., dianteira dir.
RODAS = BiLista([("traseiro esquerdo", "rear left"), ("traseiro direito", "rear right"),
                ("dianteiro esquerdo", "front left"), ("dianteiro direito", "front right")])
RODAS_COL = ["TE", "TD", "DE", "DD"]
PISTAS_LEMBRADAS = set()   # para lembrar o acerto anterior só uma vez por pista

PADRAO_CONFIG = {
    "idioma": "pt",
    "porta": 20777,
    "encaminhar_para": ["127.0.0.1:20778"],
    "voz_ativada": True,
    "voz_motor": "neural",
    "voz_neural": "pt-BR-AntonioNeural",
    "voz_neural_en": "en-GB-RyanNeural",
    "voz_efeito_radio": True,
    "voz_velocidade_neural": "+8%",
    "nome_piloto": "",
    "distancia_corrida_pct": 50,
    "voz_no_notebook": True,
    "painel": True,
    "porta_painel": 8080,
    "painel_no_celular": True,          # False: o painel só abre neste computador
    "verificar_atualizacoes": True,     # procura versão nova no GitHub ao abrir
    "abrir_painel_automaticamente": True,
    "velocidade_voz": 1,
    "volume_voz": 100,
    "botoes_udp": {"1": "situacao", "2": "pneus", "3": "estrategia", "4": "repetir", "5": "ouvir", "6": "teste_radio",
                   "7": "rivais"},
    "rivais": "",
    "microfone": True,
    "microfone_palavra_ativacao": "engenheiro",
    "microfone_som_escuta": True,
    "microfone_frases": "whisper-small",
    "microfone_segundos_apos_botao": 5,
    "gravar_telemetria": True,
    "taxa_gravacao_hz": 10,
    "pasta_sessoes": "sessoes",
    "avisos": {
        "tempo_de_volta_treino_classificacao": True,
        "tempo_de_volta_corrida": False,
        "posicao_e_diferencas_a_cada_voltas": 3,
        "carro_de_tras_perto_segundos": 1.0,
        "desgaste_pneus_alertas": [40, 60, 70],
        "janela_de_parada": True,
        "combustivel": True,
        "clima": True,
        "comparar_pneus_chuva_seco": True,
        "classificacao_minutos_finais": 3,
        "classificacao_zona_de_corte": True,
        "safety_car": True,
        "dano_asa_dianteira_percentual": 25,
        "penalidades": True,
        "ultimas_voltas": True,
        "temperatura_pneu_alta_celsius": 0,
        "delta_por_setor_classificacao": True,
        "pits_dos_rivais": True,
        "lembrar_acertos_anteriores": True,
        "pecas_motor_alertas": [70, 85],
        "abandonos_e_incidentes": True,
        "carros_lentos": True,
        "estrategia_rivais": True,
    },
}


def iv(x, padrao=0):
    """Converte enum/None em int."""
    if x is None:
        return padrao
    try:
        return int(x.value)
    except AttributeError:
        try:
            return int(x)
        except (TypeError, ValueError):
            return padrao


def tempo_txt(ms):
    """1:15.258"""
    if not ms or ms <= 0:
        return "-"
    m, resto = divmod(int(ms), 60000)
    s, mil = divmod(resto, 1000)
    return f"{m}:{s:02d}.{mil:03d}" if m else f"{s}.{mil:03d}"


PALAVRAS_COMUNS = {"volta", "dano", "pneus", "pneu", "box", "safety", "atenção", "chuva", "perdemos", "perdeu",
                   "ganhou", "faltam", "última", "defenda", "combustível", "penalidade", "advertência",
                   "previsão", "começou", "a", "o", "os", "as", "agora", "janela", "estratégia", "parada",
                   "bandeira", "pista", "setor", "você", "isso", "boa", "bela", "manobra", "vitória", "que",
                   # inglês
                   "lap", "tyres", "careful", "rain", "we", "lost", "gained", "last", "defend", "fuel", "penalty",
                   "track", "forecast", "it", "it's", "the", "now", "window", "strategy", "stop", "sector", "you",
                   "good", "great", "nice", "what", "only", "cars", "chequered", "stay", "time", "overtake",
                   "drive-through", "position", "pit", "push", "damage", "watch", "rejoined", "two", "one",
                   "front", "rear", "fastest", "your", "he", "they", "there", "both", "end", "personal", "purple",
                   "green", "copy", "radio", "nothing", "no", "yes", "all", "if", "under", "on", "in", "for", "out",
                   "under", "rain", "heavy", "light", "parts", "turbo", "battery", "gearbox", "engine", "sector", "lights",
                   "five", "three", "box,", "mediums", "alto", "perfeito", "ótimo", "recebido", "te", "teste",
                   "loud", "perfect", "great", "copy", "i", "softs", "hards", "intermediates", "wets", "today", "that's"}


def falas_pneu(comp):
    return PNEU_VISUAL.get(comp, "pneu")


def tempo_fala(ms):
    """'1 minuto, 9 segundos e 845' (para a voz)."""
    import falas as _f
    return _f.tempo(ms)


def seg_fala(segundos, casas=1):
    """0.43 -> '0 vírgula 4'"""
    v = abs(segundos)
    txt = f"{v:.{casas}f}"
    inteiro, _, dec = txt.partition(".")
    return f"{inteiro} vírgula {dec}" if dec else inteiro


def sem_acento(txt):
    trocas = str.maketrans("áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ ", "aaaaeeiooouc" "AAAAEEIOOOUC" "_")
    return "".join(c for c in txt.translate(trocas) if c.isalnum() or c in "_-")


def _idioma_do_sistema():
    """Primeira vez: português se o Windows estiver em português, senão inglês."""
    try:
        import locale
        nome = (locale.getlocale()[0] or "") + " " + (os.environ.get("LANG") or "")
        if os.name == "nt":
            import ctypes
            nome += " " + {1046: "pt_BR", 2070: "pt_PT"}.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), "")
        return "pt" if "pt" in nome.lower() or "portug" in nome.lower() else "en"
    except Exception:  # noqa: BLE001
        return "en"


def carregar_config():
    caminho = os.path.join(AQUI, "config.json")
    cfg = json.loads(json.dumps(PADRAO_CONFIG))
    if not os.path.exists(caminho):
        cfg["idioma"] = _idioma_do_sistema()
        cfg["_novo"] = True                   # primeira vez: o painel mostra o assistente de boas-vindas
    if os.path.exists(caminho):
        try:
            with open(caminho, encoding="utf-8-sig") as f:
                usuario = json.load(f)
            avisos = usuario.pop("avisos", {})
            botoes = usuario.pop("botoes_udp", None)
            cfg.update(usuario)
            cfg["avisos"].update(avisos)
            if isinstance(botoes, dict):
                cfg["botoes_udp"].update(botoes)
        except Exception as e:  # noqa: BLE001
            print(f"[AVISO] Não consegui ler o config.json ({e}). Usando o padrão.")
    idioma.definir(cfg.get("idioma", "pt"))
    return cfg


def ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "?"


ATUALIZACAO = {}   # {"versao": "1.0.1", "link": "..."} quando há versão nova no GitHub


def _versao_tupla(txt):
    try:
        return tuple(int(x) for x in str(txt).strip().lstrip("vV").split("-")[0].split("."))
    except ValueError:
        return ()


def verificar_atualizacao():
    """Procura uma versão mais nova na página de versões do GitHub (uma vez, em segundo plano)."""
    import versao
    if not versao.USUARIO_GITHUB:
        return
    try:
        import urllib.request
        url = f"https://api.github.com/repos/{versao.USUARIO_GITHUB}/engenheiro/releases/latest"
        req = urllib.request.Request(url, headers={"User-Agent": f"{versao.NOME}/{versao.VERSAO}",
                                                   "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            dados = json.loads(r.read().decode("utf-8"))
        nova = str(dados.get("tag_name") or "").lstrip("vV")
        if _versao_tupla(nova) > _versao_tupla(versao.VERSAO):
            ATUALIZACAO.update({"versao": nova, "link": dados.get("html_url") or versao.LINK_GITHUB})
            print(f"[APP] Versão nova disponível: {nova} ({ATUALIZACAO['link']})")
    except Exception:  # noqa: BLE001   (sem internet, GitHub fora do ar...: tenta na próxima vez)
        pass


# --------------------------------------------------------------------------------------
# Voz (rádio)
# --------------------------------------------------------------------------------------



class Radio:
    """Fila de mensagens faladas. Mensagens antigas são descartadas para não falar coisa velha."""

    def __init__(self, cfg, ativada=True):
        self._fila = []
        self._seq = itertools.count()
        self._cond = threading.Condition()
        self._ultimas = {}
        self.nome_piloto = (cfg.get("nome_piloto") or "").strip()
        self._ultimo_nome = -9999.0
        self.historico = deque(maxlen=40)      # para o painel
        self.audios = {}                       # id -> wav (para tocar no painel)
        self._ids = itertools.count(1)
        self.no_notebook = bool(cfg.get("voz_no_notebook", True))
        self.silencioso = False      # "silêncio": só avisos importantes
        self._falando = False
        self.neural = None
        self.windows = None
        self._neural_falhou_em = None
        self._cfg = cfg
        if ativada:
            self._iniciar_voz()
        threading.Thread(target=self._laco, daemon=True).start()

    def _iniciar_voz(self):
        import voz
        cfg = self._cfg
        if str(cfg.get("voz_motor", "neural")).lower() == "neural":
            lang = "en" if idioma.en() else "pt"
            escolhida = cfg.get("voz_neural_en" if lang == "en" else "voz_neural", "")
            self.neural = voz.VozNeural(voz.voz_do_idioma(escolhida, lang),
                                        cfg.get("voz_velocidade_neural", "+8%"),
                                        bool(cfg.get("voz_efeito_radio", True)))
            if self.neural.ok:
                efeito = " com efeito de rádio" if self.neural.efeito else ""
                print(f"[VOZ] Voz neural: {self.neural.voz}{efeito} (precisa de internet).")
            else:
                self.neural = None
        if os.name != "nt":
            if not self.neural:
                print("[VOZ] Voz do Windows indisponível neste sistema. Os avisos vão aparecer apenas na tela.")
            return
        self.windows = voz.VozWindows(cfg.get("velocidade_voz", 1), cfg.get("volume_voz", 100),
                                      "en" if idioma.en() else "pt")
        if self.windows.ok and not self.neural:
            if self.windows.nome == "SEM_PORTUGUES":
                print("[VOZ] Nenhuma voz em português instalada no Windows; vou usar a voz padrão.")
                print("      Para instalar: Configurações > Hora e idioma > Fala > Adicionar vozes > Português (Brasil).")
            else:
                print(f"[VOZ] Usando a voz do Windows: {self.windows.nome}")
        elif not self.windows.ok and not self.neural:
            print("[VOZ] Não consegui iniciar nenhuma voz. Os avisos vão aparecer apenas na tela.")

    def falar(self, texto, prioridade=1, chave=None, intervalo=0.0):
        """prioridade: 0 = info, 1 = normal, 2 = importante, 3 = urgente."""
        agora = time.monotonic()
        if chave:
            ultima = self._ultimas.get(chave)
            if ultima is not None and agora - ultima < intervalo:
                return False
            self._ultimas[chave] = agora
        # o nome só nos avisos importantes, e não toda hora
        espera_nome = 90 if prioridade >= 3 else 240
        if (self.nome_piloto and prioridade >= 2 and agora - self._ultimo_nome > espera_nome
                and not texto.startswith(self.nome_piloto)):
            primeira = texto.split(" ", 1)[0].strip(".,!:")
            if primeira.lower() in PALAVRAS_COMUNS:     # "Yohan, volta invalidada" (não "Volta")
                texto = texto[0].lower() + texto[1:]
            texto = f"{self.nome_piloto}, {texto}"
            self._ultimo_nome = agora
        if self.silencioso and prioridade < 2:
            print(f"{datetime.now():%H:%M:%S} [RÁDIO - silêncio] {texto}", flush=True)
            return False
        print(f"{datetime.now():%H:%M:%S} [RÁDIO] {texto}", flush=True)
        item = {"id": next(self._ids), "hora": datetime.now().strftime("%H:%M:%S"), "texto": texto,
                "prio": prioridade, "audio": False}
        self.historico.append(item)
        with self._cond:
            heapq.heappush(self._fila, (-prioridade, next(self._seq), agora, item))
            self._cond.notify()
        return True

    def esta_falando(self):
        with self._cond:
            return self._falando or bool(self._fila)

    def teste_de_radio(self):
        """O piloto pediu (ou respondeu) o teste de rádio."""
        agora = time.monotonic()
        if agora - getattr(self, "teste_pedido_em", -999) < 90:      # respondeu ao nosso teste
            self.teste_pedido_em = -999
            txt = falas.escolher(tr("Perfeito, te ouço alto e claro também. Bom trabalho hoje.",
                                    "Perfect, loud and clear on our side too. Have a good one."),
                                 tr("Ótimo, rádio ok dos dois lados. Vamos com tudo.",
                                    "Great, radio is good both ways. Let's go."))
        else:
            txt = falas.escolher(tr("Alto e claro. Rádio funcionando.", "Loud and clear. Radio is working."),
                                 tr("Te ouço alto e claro. Rádio ok.", "I hear you loud and clear. Radio check okay."),
                                 tr("Recebido, alto e claro.", "Copy, loud and clear."))
        self.falar(txt, 2, None)

    def pedir_teste_de_radio(self):
        """O engenheiro chama o teste de rádio (antes da corrida), esperando o piloto responder pelo microfone."""
        self.teste_pedido_em = time.monotonic()
        self.falar(falas.escolher(tr("Teste de rádio. Se estiver me ouvindo, diga: alto e claro.",
                                     "Radio check. If you can hear me, say: loud and clear."),
                                  tr("Teste de rádio, um, dois. Está me ouvindo?",
                                     "Radio check, one, two. How do you hear me?")), 1, "teste-radio", 600)

    def repetir_ultima(self):
        for item in reversed(self.historico):
            if not item["texto"].startswith("(repetindo)"):
                self.falar(item["texto"], 2)
                return
        self.falar(tr("Nada para repetir ainda.", "Nothing to repeat yet."), 1)

    def _falar_agora(self, item):
        import voz
        texto = item["texto"]
        agora = time.monotonic()
        if self.neural and (self._neural_falhou_em is None or agora - self._neural_falhou_em > 300):
            try:
                wav = self.neural.gerar_wav(texto)
                self.audios[item["id"]] = wav
                item["audio"] = True
                for velho in [k for k in self.audios if k < item["id"] - 30]:
                    self.audios.pop(velho, None)
                if self.no_notebook:
                    voz.tocar_wav(wav)
                else:   # só no painel: espera o tempo da frase para não embolar
                    time.sleep(max(0.5, (len(wav) - 44) / (2 * voz.TAXA)))
                self._neural_falhou_em = None
                return
            except Exception as e:  # noqa: BLE001
                if self._neural_falhou_em is None:
                    print(f"[VOZ] Voz neural falhou ({e}). Usando a voz do Windows por enquanto.")
                self._neural_falhou_em = agora
        if self.windows and self.no_notebook:
            self.windows.falar(texto)

    def _laco(self):
        while True:
            with self._cond:
                while not self._fila:
                    self._cond.wait()
                neg_prio, _, criado, item = heapq.heappop(self._fila)
                self._falando = True
            validade = 12 + 10 * (-neg_prio)
            if time.monotonic() - criado <= validade:
                try:
                    self._falar_agora(item)
                except Exception:  # noqa: BLE001
                    pass
            with self._cond:
                self._falando = False

    def esperar_fila(self, limite=60):
        fim = time.monotonic() + limite
        time.sleep(0.3)
        while time.monotonic() < fim:
            with self._cond:
                if not self._fila and not getattr(self, "_falando", False):
                    break
            time.sleep(0.2)


# --------------------------------------------------------------------------------------
# Estado de cada carro
# --------------------------------------------------------------------------------------

class Carro:
    def __init__(self, idx):
        self.idx = idx
        self.nome = f"Carro {idx + 1}"
        self.volta = 0
        self.s1 = 0
        self.s2 = 0
        self.invalida = False
        self.teve_pit = False
        self.ultima_ms = 0
        self.ultima_volta_num = 0
        self.ultima_valida = False
        self.ultima_teve_pit = False
        self.melhor_ms = 0
        self.posicao = 0
        self.pneu = 0
        self.idade_pneu = 0
        self.desgaste = [0.0, 0.0, 0.0, 0.0]
        self.dif_frente_ms = 0
        self.status_resultado = 0
        self.status_piloto = 0
        self.dist_volta = -1.0
        self.pos_ant = 0
        self.pit_status = 0
        self.paradas = 0
        self.dif_lider_ms = 0
        self.equipe = -1
        self.x = None
        self.z = None
        self.ativo = False
        self.vel = None
        self.setor = -1


# Curvas oficiais de cada pista (id do jogo): número da curva e posição como fração da volta,
# a partir da linha de chegada. Fonte: dados de cronometragem da F1 (mapas/curvas.json).
try:
    with open(os.path.join(AQUI, "mapas", "curvas.json"), encoding="utf-8") as _f:
        CURVAS_OFICIAIS = {int(k): v["curvas"] for k, v in json.load(_f).items()}
except (OSError, ValueError, KeyError):
    CURVAS_OFICIAIS = {}
CURVAS_POR_PISTA = {k: len(v) for k, v in CURVAS_OFICIAIS.items()}


class MapaPista:
    """Monta o desenho da pista a partir das posições dos carros (por distância na volta)."""
    PASSO = 10.0

    def __init__(self, pista, comprimento):
        self.pista = pista
        self.comprimento = comprimento
        self.n = max(10, int(comprimento / self.PASSO) + 1)
        self.acum = [[0.0, 0.0, 0] for _ in range(self.n)]
        self.completo = False
        self.versao = 0
        self._pontos = []
        self._ultimo_calc = 0.0
        self._salvo = False
        self.tf = None
        self.limites_setor = []     # distâncias (m) onde começam o setor 2 e o 3
        self.marcas = {}            # "largada"/"s2"/"s3" -> [x, z] no mundo do jogo
        self.extras = {}            # "overtake": [[x, z], ...], "speed_trap": [x, z], "speed_trap_kmh": n
        self.indice = [[0.0, 0.0, 0] for _ in range(self.n)]   # distância na volta -> posição (todos os carros)
        self.curvas_pos = []        # [["1", x, z], ...] curvas oficiais já localizadas no traçado do jogo
        self.arquivo = os.path.join(AQUI, "mapas", f"pista_{pista}.json")
        self.arquivo_marcas = os.path.join(AQUI, "mapas", f"marcas_{pista}.json")
        try:
            with open(self.arquivo_marcas, encoding="utf-8") as f:
                m = json.load(f)
            if abs((m.get("comprimento") or 0) - comprimento) < 50:
                self.marcas = {k: m[k] for k in ("largada", "s2", "s3") if k in m}
                self.extras = m.get("extras") or {}
                self.curvas_pos = m.get("curvas_pos") or []
        except (OSError, ValueError):
            pass
        try:
            with open(self.arquivo, encoding="utf-8") as f:
                d = json.load(f)
            comp = d.get("comprimento") or 0
            if (not comp or abs(comp - comprimento) < 50) and len(d.get("pontos", [])) > 20:
                self._pontos = d["pontos"]
                self.tf = d.get("tf")
                self.completo = self._salvo = True
                self.versao = 1
        except (OSError, ValueError):
            pass

    def adicionar(self, dist, x, z):
        if dist < 0 or dist >= self.comprimento:
            return
        k = self.indice[int(dist / self.PASSO)]
        if k[2] < 50:
            k[0] += x
            k[1] += z
            k[2] += 1
        if self.completo:
            return
        a = self.acum[int(dist / self.PASSO)]
        a[0] += x
        a[1] += z
        a[2] += 1

    def marcar(self, dist, x, z):
        """Guarda onde ficam a linha de chegada e o início dos setores (para desenhar no mapa)."""
        if len(self.marcas) >= 3 or dist < 0:
            return
        for nome, alvo in (("largada", 0.0), ("s2", self.limites_setor[0] if self.limites_setor else 0),
                           ("s3", self.limites_setor[1] if len(self.limites_setor) > 1 else 0)):
            if nome in self.marcas or (nome != "largada" and not alvo):
                continue
            perto = (dist < 8 or dist > self.comprimento - 8) if nome == "largada" else abs(dist - alvo) < 8
            if perto:
                self.marcas[nome] = [round(x, 1), round(z, 1)]
                self.versao += 1
                if len(self.marcas) == 3:   # guarda para a próxima vez já abrir com os setores
                    self.salvar_marcas()

    def salvar_marcas(self):
        try:
            with open(self.arquivo_marcas, "w", encoding="utf-8") as f:
                json.dump(dict(self.marcas, comprimento=self.comprimento, extras=self.extras,
                               curvas_pos=self.curvas_pos), f)
        except OSError:
            pass

    def marcar_overtake(self, x, z):
        """Ponto onde o Overtake fica disponível (aprendido pelo pacote de 2026)."""
        lista = self.extras.setdefault("overtake", [])
        if any((x - a) ** 2 + (z - b) ** 2 < 60 ** 2 for a, b in lista):
            return
        lista.append([round(x, 1), round(z, 1)])
        self.versao += 1
        self.salvar_marcas()

    def marcar_speed_trap(self, x, z, kmh):
        if kmh <= self.extras.get("speed_trap_kmh", 0):
            return
        self.extras["speed_trap"] = [round(x, 1), round(z, 1)]
        self.extras["speed_trap_kmh"] = int(kmh)
        self.versao += 1
        self.salvar_marcas()

    def _localizar_curvas(self):
        """Coloca no traçado do jogo as curvas oficiais (pela fração da volta de cada uma)."""
        oficiais = CURVAS_OFICIAIS.get(self.pista)
        if not oficiais or self.curvas_pos:
            return
        pos = []
        for rot, frac in oficiais:
            b = min(self.n - 1, int(frac * self.comprimento / self.PASSO))
            viz = [self.indice[j] for j in (b - 1, b, b + 1) if 0 <= j < self.n and self.indice[j][2] >= 2]
            if not viz:
                return            # ainda falta algum carro passar por essa curva
            n = sum(v[2] for v in viz)
            pos.append([rot, round(sum(v[0] for v in viz) / n, 1), round(sum(v[1] for v in viz) / n, 1)])
        self.curvas_pos = pos
        self.versao += 1
        self.salvar_marcas()

    def atualizar(self):
        agora = time.monotonic()
        if agora - self._ultimo_calc < 2.0:
            return
        self._ultimo_calc = agora
        self._localizar_curvas()
        if self.completo:
            return
        pts = [[round(a[0] / a[2], 1), round(a[1] / a[2], 1)] if a[2] else None for a in self.acum]
        cheios = sum(1 for a in self.acum if a[2] >= 3)
        self._pontos = pts
        self.versao += 1
        if cheios / self.n >= 0.97:
            self.completo = True
            self._pontos = [p for p in pts if p]
            try:
                os.makedirs(os.path.dirname(self.arquivo), exist_ok=True)
                with open(self.arquivo, "w", encoding="utf-8") as f:
                    json.dump({"pista": self.pista, "comprimento": self.comprimento, "pontos": self._pontos}, f)
                self._salvo = True
            except OSError:
                pass

    def dados(self):
        return {"versao": self.versao, "completo": self.completo, "pontos": self._pontos, "tf": self.tf,
                "marcas": self.marcas, "extras": self.extras, "curvas": CURVAS_POR_PISTA.get(self.pista, 0),
                "curvas_pos": self.curvas_pos,
                "comprimento": self.comprimento}


# --------------------------------------------------------------------------------------
# Sessão: gravação + regras do engenheiro
# --------------------------------------------------------------------------------------

class Sessao:
    def __init__(self, uid, cfg, radio):
        self.uid = uid
        self.cfg = cfg
        self.av = cfg["avisos"]
        self.radio = radio
        self.inicio = datetime.now()
        self.formato = 2025
        self.jogador = 0
        self.carros = [Carro(i) for i in range(24)]
        self.n_carros_ativos = 0

        # informações da sessão
        self.info_ok = False
        self.tipo = 0
        self.pista = -1
        self.clima = 0
        self.temp_pista = 0
        self.temp_ar = 0
        self.total_voltas = 0
        self.tempo_restante = 0
        self.duracao = 0
        self.safety_car = 0
        self.pit_ideal = 0
        self.pit_limite = 0
        self.previsao = []
        self.clima_inicial = None

        # jogador
        self.voltas = []            # linhas da tabela de voltas
        self.volta_atual = 0
        self.acum = self._novo_acum()
        self.tipo_volta = set()
        self.melhor_ms = 0
        self.melhor_setores = [0, 0, 0]
        self.combustivel = 0.0
        self.comb_sobra_voltas = 0.0
        self.ers = 0.0
        self.ers_modo = 0
        self.telemetria = None
        self.dano = {}
        self.acertos = []
        self.eventos = []
        self.paradas = 0
        self.posicao = 0
        self.posicao_largada = 0
        self.posicao_final = 0
        self.stint_inicio_volta = 1
        self.stint_desgaste_voltas = []   # desgaste máx. ao fim de cada volta do stint
        self.alertas_desgaste_feitos = set()
        self.alerta_dano_feito = 0
        self.penalidades_seg = 0
        self.advertencias = 0
        self.drive_through = 0
        self.stop_go = 0
        self.pos_pendente = None
        self.pos_anunciada = 0
        self.tempo_sessao = 0.0
        self.conjuntos = []          # jogos de pneus do jogador: dicts (composto, desgaste, disponível, montado, vida)
        self.compostos_usados = set()
        self.plano = None            # melhor plano de paradas calculado na corrida
        self.plano_anunciado = None  # (volta da 1ª parada, composto) já falado
        self._plano_volta_falada = -9
        self.aero_modo = ""          # 2026: "straight" ou "curva"
        self.overtake_estado = ""    # 2026: "ativo", "disponivel" ou ""
        self.overtake_dist = 0
        self._ot_disp_ant = False
        self.equipe_por_id = {}      # id de equipe do jogo -> equipe (aprendido pelos nomes)
        self.hist_dist = {}         # idx -> deque[(tempo da sessão, distância total)] para calcular diferenças
        self.pos_foto = {}          # idx -> (posição, paradas) quando a sua posição foi anunciada
        self.ultrapassagens = []    # (hora, quem passou, quem foi passado) dos eventos OVTK com você
        self.viu_ovtk = False
        self.voltando_box = False
        self.fim_box = None
        self.carro_tras_perto = False
        self.ult_status_resultado = 0
        self.avisos_feitos = set()
        self.ultimo_pneu_jogador = 0
        self.ultima_idade_pneu = 0
        self.pausado = False

        # painel
        self.mapa = None
        self.comprimento_pista = 0
        self.rpm_max = 13000
        self.drs_permitido = 0
        self.tempo_volta_atual = 0
        self.melhores_sessao = [0, 0, 0, 0]   # s1, s2, s3, volta (todos os carros)
        self.rejoin = 0
        # delta ao vivo
        self.traco_atual = []          # (distância, tempo ms) da volta em andamento
        self.traco_ref = None          # da melhor volta: ([distâncias], [tempos])
        self.delta_ms = None
        self._ult_setor = 0
        # relatório
        self.amostras_volta = []       # amostras da volta em andamento
        self.tracos = {}               # volta -> {"tempo", "valida", "amostras"}
        # rivais
        self.rivais_no_pit = {}
        self.vigia = vigia.Vigia(self, CURVAS_OFICIAIS)
        self.estrutura = []
        self.dono_volta_rapida = -1
        self.hist_gaps = []           # (volta, idx da frente, dif frente, idx de trás, dif trás)
        self.fim_quali_falado = False
        self.pecas = {}                 # nome -> desgaste % (unidade de potência e câmbio)
        self.pecas_alertas_feitos = set()
        self.falha = {}
        self.acerto_lembrado = False
        self.ultimo_pacote = time.monotonic()

        # arquivos
        self.pasta = None
        self._arq = {}
        self._csv = {}
        self._ultima_tele = -999.0

    # ---------------- utilitários ----------------
    @staticmethod
    def _novo_acum():
        return {"amostras": 0, "acel_soma": 0.0, "acel_cheio": 0, "freio": 0, "vel_max": 0,
                "fora_pista": 0, "comb_ini": None, "desg_ini": None, "temp_tras": [], "pit": False, "sc": False,
                "quente": [0, 0, 0, 0]}

    @property
    def nome_sessao(self):
        return SESSOES.get(self.tipo, tr("Sessão", "Session") + f" {self.tipo}")

    @property
    def nome_pista(self):
        return PISTAS.get(self.pista, f"Pista {self.pista}")

    @property
    def eh_corrida(self):
        return self.tipo in SESSOES_CORRIDA

    @property
    def eh_classif(self):
        return self.tipo in SESSOES_CLASSIF

    @property
    def eu(self):
        return self.carros[self.jogador]

    def _nome(self, idx):
        if idx is None or idx < 0 or idx >= len(self.carros):
            return ""
        n = self.carros[idx].nome
        return "" if n.startswith("Carro ") or n.lower() in ("player", "jogador", "") else n

    def falar(self, texto, prioridade=1, *a, **k):
        ok = self.radio.falar(texto, prioridade, *a, **k)
        if ok is not False:
            try:
                self._escrever("radio", {"hora": datetime.now().strftime("%H:%M:%S"), "volta": self.volta_atual,
                                         "prioridade": prioridade, "mensagem": texto})
            except Exception:  # noqa: BLE001
                pass
        return ok

    def evento(self, texto):
        self.eventos.append((datetime.now().strftime("%H:%M:%S"), self.volta_atual, texto))
        self._escrever("eventos", {"hora": datetime.now().strftime("%H:%M:%S"),
                                   "volta": self.volta_atual, "evento": texto})

    # ---------------- arquivos ----------------
    def _abrir_pasta(self):
        if self.pasta or not self.cfg.get("gravar_telemetria", True):
            return
        base = self.cfg.get("pasta_sessoes", "sessoes")
        if not os.path.isabs(base):
            base = os.path.join(AQUI, base)
        nome = f"{self.inicio:%Y-%m-%d_%H%M}_{sem_acento(self.nome_pista)}_{sem_acento(self.nome_sessao)}"
        self.pasta = os.path.join(base, nome)
        os.makedirs(self.pasta, exist_ok=True)
        print(f"[GRAVAÇÃO] Salvando em: {self.pasta}")

    COLUNAS = {
        "telemetria": ["tempo_sessao", "volta", "dist_volta_m", "setor", "velocidade_kmh", "acelerador",
                       "freio", "volante", "marcha", "rpm", "drs", "ers_modo", "ers_bateria_mj",
                       "combustivel_kg", "comb_sobra_voltas", "pneu", "idade_pneu"]
                      + [f"desgaste_{r}" for r in RODAS_COL]
                      + [f"temp_sup_{r}" for r in RODAS_COL]
                      + [f"temp_int_{r}" for r in RODAS_COL]
                      + [f"temp_freio_{r}" for r in RODAS_COL]
                      + [f"pressao_{r}" for r in RODAS_COL]
                      + [f"superficie_{r}" for r in RODAS_COL]
                      + ["posicao", "dif_frente_s", "dif_lider_s", "pit_status", "volta_invalida"],
        "voltas": ["volta", "tempo", "tempo_ms", "s1_ms", "s2_ms", "s3_ms", "valida", "tipo", "teve_pit",
                   "pneu", "idade_pneu", "posicao", "desgaste_max_fim", "desgaste_na_volta",
                   "combustivel_fim_kg", "consumo_volta_kg", "vel_max_kmh", "acel_media_pct",
                   "acel_cheio_pct", "freio_pct", "fora_pista_pct", "temp_sup_tras_media", "clima",
                   "temp_pista"],
        "voltas_todos": ["volta", "carro", "piloto", "tempo", "tempo_ms", "s1_ms", "s2_ms", "s3_ms",
                         "valida", "teve_pit", "pneu", "idade_pneu", "posicao"],
        "eventos": ["hora", "volta", "evento"],
        "radio": ["hora", "volta", "prioridade", "mensagem"],
    }

    def _escrever(self, nome, linha):
        if not self.cfg.get("gravar_telemetria", True) or not self.info_ok:
            return
        self._abrir_pasta()
        if nome not in self._csv:
            arq = open(os.path.join(self.pasta, f"{nome}.csv"), "w", newline="", encoding="utf-8-sig")
            w = csv.DictWriter(arq, fieldnames=self.COLUNAS[nome], delimiter=";", extrasaction="ignore")
            w.writeheader()
            self._arq[nome] = arq
            self._csv[nome] = w
        self._csv[nome].writerow(linha)
        if nome != "telemetria":
            self._arq[nome].flush()

    def fechar(self):
        self.escrever_resumo()
        self._salvar_historico_acerto()
        self._gerar_relatorio()
        self._analise_final(falar=False)
        for a in self._arq.values():
            try:
                a.close()
            except OSError:
                pass
        self._arq.clear()
        self._csv.clear()

    # ---------------- pacotes ----------------
    def on_sessao(self, p):
        primeira = not self.info_ok
        self.tipo = iv(p.m_sessionType)
        self.pista = iv(p.m_trackId, -1)
        clima_antes = self.clima
        self.clima = iv(p.m_weather)
        self.temp_pista = iv(p.m_trackTemperature)
        self.temp_ar = iv(p.m_airTemperature)
        self.total_voltas = iv(p.m_totalLaps)
        self.tempo_restante = iv(p.m_sessionTimeLeft)
        self.duracao = iv(p.m_sessionDuration)
        sc_antes = self.safety_car
        self.safety_car = iv(p.m_safetyCarStatus)
        self.pit_ideal = iv(getattr(p, "m_pitStopWindowIdealLap", 0))
        self.pit_limite = iv(getattr(p, "m_pitStopWindowLatestLap", 0))
        self.rejoin = iv(getattr(p, "m_pitStopRejoinPosition", 0))
        self.pausado = bool(iv(getattr(p, "m_gamePaused", 0)))
        self.comprimento_pista = iv(getattr(p, "m_trackLength", 0))
        if self.mapa is None and self.comprimento_pista > 500 and self.pista >= 0:
            self.mapa = MapaPista(self.pista, self.comprimento_pista)
        if self.mapa is not None and not self.mapa.limites_setor:
            s2 = float(getattr(p, "m_sector2LapDistanceStart", 0) or 0)
            s3 = float(getattr(p, "m_sector3LapDistanceStart", 0) or 0)
            if 0 < s2 < s3 < self.comprimento_pista:
                self.mapa.limites_setor = [s2, s3]
        self.previsao = [(iv(s.m_sessionType), iv(s.m_timeOffset), iv(s.m_weather), iv(s.m_rainPercentage))
                         for s in (p.m_weatherForecastSamples or [])]
        self.estrutura = [iv(x) for x in (getattr(p, "m_weekendStructure", None) or [])]
        self.info_ok = True

        if self.temp_pista > 0 and (not self.clima_inicial or not self.clima_inicial[1]):
            self.clima_inicial = (self.clima, self.temp_pista, self.temp_ar)
        if primeira:
            if not self.clima_inicial:
                self.clima_inicial = (self.clima, self.temp_pista, self.temp_ar)
            txt = (tr(f"{self.nome_sessao} em {self.nome_pista}. ", f"{self.nome_sessao} in {self.nome_pista}. ")
                   + CLIMA.get(self.clima, '').capitalize()
                   + (tr(f", pista a {self.temp_pista} graus.", f", track temperature {self.temp_pista} degrees.")
                      if self.temp_pista > 0 else "."))
            if self.eh_classif:
                txt += tr(" A pista melhora a cada volta: deixe a última tentativa para o fim.",
                          " The track gets faster every lap: save your last attempt for the end.")
            elif self.tipo in SESSOES_TREINO and falas.dica(self.pista):
                txt += tr(f" Dica para esta pista: {falas.dica(self.pista)}.", f" Tip for this track: {falas.dica(self.pista)}.")
            self.falar(txt, 1, "inicio")
            if self.eh_corrida and self.cfg.get("microfone", True):
                self.radio.pedir_teste_de_radio()
            return

        if self.av["clima"]:
            self._regra_clima(clima_antes)
        if self.av["safety_car"] and self.eh_corrida:
            self._regra_safety_car(sc_antes)
        if self.eh_classif:
            self._regra_minutos_finais()

    def on_participantes(self, p):
        self.n_carros_ativos = iv(p.m_numActiveCars)
        for i, part in enumerate(p.m_participants or []):
            if i < len(self.carros):
                self.carros[i].equipe = iv(getattr(part, "m_teamId", -1), -1)
                self.carros[i].ativo = i < self.n_carros_ativos
                nome = getattr(part, "m_name", "") or ""
                if isinstance(nome, bytes):
                    nome = nome.decode("utf-8", "ignore")
                nome = nome.strip("\x00 ").strip()
                if nome:
                    self.carros[i].nome = nome.title() if nome.isupper() else nome
        for c in self.carros:          # ids que não conheço: aprende pela maioria dos nomes dos pilotos
            eq = equipe_do_nome(c.nome)
            if eq and c.equipe >= 0 and c.equipe not in ID_EQUIPE and c.idx != self.jogador:
                self.equipe_por_id.setdefault(c.equipe, eq)

    def on_acerto(self, p):
        try:
            a = p.m_carSetups[self.jogador]
        except (IndexError, TypeError):
            return
        campos = ["m_frontWing", "m_rearWing", "m_onThrottle", "m_offThrottle", "m_frontCamber",
                  "m_rearCamber", "m_frontToe", "m_rearToe", "m_frontSuspension", "m_rearSuspension",
                  "m_frontAntiRollBar", "m_rearAntiRollBar", "m_frontSuspensionHeight",
                  "m_rearSuspensionHeight", "m_brakePressure", "m_brakeBias", "m_engineBraking",
                  "m_frontLeftTyrePressure", "m_frontRightTyrePressure", "m_rearLeftTyrePressure",
                  "m_rearRightTyrePressure", "m_fuelLoad"]
        atual = {c[2:]: round(float(getattr(a, c, 0) or 0), 2) for c in campos}
        if not any(atual.values()):
            return
        if not self.acertos or self.acertos[-1][1] != atual:
            self.acertos.append((self.volta_atual, atual))
        if (not self.acerto_lembrado and self.info_ok and self.av.get("lembrar_acertos_anteriores", True)
                and self.pista not in PISTAS_LEMBRADAS):
            self.acerto_lembrado = True
            PISTAS_LEMBRADAS.add(self.pista)
            self._lembrar_acerto()

    def on_status(self, p):
        for i, st in enumerate(p.m_carStatusData or []):
            if i >= len(self.carros):
                break
            c = self.carros[i]
            c.pneu = iv(st.m_visualTyreCompound)
            c.idade_pneu = iv(st.m_tyresAgeLaps)
        st = p.m_carStatusData[self.jogador]
        self.rpm_max = iv(st.m_maxRPM) or self.rpm_max
        self.drs_permitido = iv(st.m_drsAllowed)
        self.combustivel = float(st.m_fuelInTank)
        self.comb_sobra_voltas = float(st.m_fuelRemainingLaps)
        self.ers = float(st.m_ersStoreEnergy)
        self.ers_modo = iv(st.m_ersDeployMode)
        # troca de pneu (novo stint)
        pneu, idade = self.eu.pneu, self.eu.idade_pneu
        if self.ultimo_pneu_jogador and (pneu != self.ultimo_pneu_jogador
                                         or (idade == 0 and self.ultima_idade_pneu >= 2)):
            self._novo_stint()
        self.ultimo_pneu_jogador, self.ultima_idade_pneu = pneu, idade
        if self.eh_corrida and pneu and self.eu.status_piloto:
            self.compostos_usados.add(pneu)
        if self.acum["comb_ini"] is None:
            self.acum["comb_ini"] = self.combustivel

    def on_dano(self, p):
        for i, d in enumerate(p.m_carDamageData or []):
            if i < len(self.carros):
                self.carros[i].desgaste = [float(x) for x in d.m_tyresWear]
                if i != self.jogador and self.eh_corrida:
                    self.vigia.dano_asa(i, max(iv(d.m_frontLeftWingDamage), iv(d.m_frontRightWingDamage)))
        d = p.m_carDamageData[self.jogador]
        self.dano = {"asa_dianteira": max(iv(d.m_frontLeftWingDamage), iv(d.m_frontRightWingDamage)),
                     "asa_traseira": iv(d.m_rearWingDamage), "assoalho": iv(d.m_floorDamage),
                     "difusor": iv(d.m_diffuserDamage), "lateral": iv(d.m_sidepodDamage)}
        if self.acum["desg_ini"] is None:
            self.acum["desg_ini"] = max(self.eu.desgaste)
        lim = self.av["dano_asa_dianteira_percentual"]
        asa = self.dano["asa_dianteira"]
        if lim and asa >= lim and asa >= self.alerta_dano_feito + 15:
            self.alerta_dano_feito = asa
            dica = tr(" Avalie trocar a asa no pit.", " Consider a new front wing at the stop.") if self.eh_corrida else ""
            self.falar(tr(f"Dano na asa dianteira: {asa} por cento.", f"Front wing damage: {asa} percent.") + dica, 2, "dano")
            self.evento(tr(f"Dano na asa dianteira {asa}%", f"Front wing damage {asa}%"))
        elif asa < lim:
            self.alerta_dano_feito = 0
        self._pecas_motor(d)

    NOMES_PECAS_BI = [("m_engineICEWear", ("Motor ICE", "Engine ICE"), ("o motor", "the engine")),
                      ("m_engineTCWear", ("Turbo", "Turbo"), ("o turbo", "the turbo")),
                      ("m_engineESWear", ("Bateria ES", "Battery ES"), ("a bateria", "the battery")),
                      ("m_engineMGUKWear", ("MGU-K", "MGU-K"), ("a MGU-K", "the MGU-K")),
                      ("m_engineCEWear", ("Eletrônica", "Electronics"), ("a eletrônica", "the electronics")),
                      ("m_engineMGUHWear", ("MGU-H", "MGU-H"), ("a MGU-H", "the MGU-H")),
                      ("m_gearBoxDamage", ("Câmbio", "Gearbox"), ("o câmbio", "the gearbox"))]

    @property
    def NOMES_PECAS(self):
        return [(a, tr(*n), tr(*f)) for a, n, f in self.NOMES_PECAS_BI]

    def _pecas_motor(self, d):
        pecas = {}
        for attr, nome, _ in self.NOMES_PECAS:
            v = iv(getattr(d, attr, 0))
            if attr == "m_engineMGUHWear" and not v:
                continue   # não existe a partir de 2026
            pecas[nome] = v
        self.pecas = pecas
        if not self.info_ok:
            return
        # falhas graves
        if iv(getattr(d, "m_engineBlown", 0)) or iv(getattr(d, "m_engineSeized", 0)):
            self.falar(tr("Perdemos o motor. Sinto muito.", "We've lost the engine. I'm sorry."), 3, "motor-quebrou", 9999)
        if iv(getattr(d, "m_ersFault", 0)):
            self.falar(tr("Falha no ERS! Vamos perder potência elétrica.", "ERS failure! We'll lose electric power."), 3, "falha-ers", 120)
        limites = sorted(self.av.get("pecas_motor_alertas") or [])
        if not limites:
            return
        primeira = not getattr(self, "_pecas_inicio_feito", False)
        if primeira:
            self._pecas_inicio_feito = True
            gastas = sorted(((pecas[nome], falado) for _, nome, falado in self.NOMES_PECAS
                             if nome in pecas and pecas[nome] >= limites[0]), reverse=True)
            if gastas:
                lista = ", ".join(tr(f"{falado} com {v} por cento", f"{falado} at {v} percent") for v, falado in gastas)
                acao = (tr("Se der, troque na tela do carro antes da classificação.",
                           "If you can, swap them in the car screen before qualifying.") if not self.eh_corrida
                        else tr("Hoje poupe o carro: evite zebras e o limitador de giro.",
                                "Look after the car today: avoid kerbs and the rev limiter."))
                self.falar(tr(f"Atenção às peças: {lista}. {acao}", f"Watch the parts: {lista}. {acao}"), 1, "pecas-inicio", 9999)
            for nome, v in pecas.items():
                for lim in limites:
                    if v >= lim:
                        self.pecas_alertas_feitos.add((nome, lim))
            return
        for attr, nome, falado in self.NOMES_PECAS:
            v = pecas.get(nome)
            if v is None:
                continue
            for lim in limites:
                if v >= lim and (nome, lim) not in self.pecas_alertas_feitos:
                    self.pecas_alertas_feitos.add((nome, lim))
                    self.falar(tr(f"{falado[0].upper() + falado[1:]} chegou a {v} por cento de desgaste. "
                                  f"Troque na tela do carro depois da sessão.",
                                  f"{falado[0].upper() + falado[1:]} is at {v} percent wear. "
                                  f"Swap it in the car screen after the session."), 1, f"peca-{nome}", 60)
                    self.evento(tr(f"{nome}: {v}% de desgaste", f"{nome}: {v}% wear"))

    def on_movimento(self, p):
        for i, m in enumerate(p.m_carMotionData or []):
            if i >= len(self.carros):
                break
            c = self.carros[i]
            c.x, c.z = float(m.m_worldPositionX), float(m.m_worldPositionZ)
            if self.mapa and c.pit_status == 0 and c.status_resultado == 2 and (c.x or c.z):
                self.mapa.adicionar(c.dist_volta, c.x, c.z)
                self.mapa.marcar(c.dist_volta, c.x, c.z)
        if self.mapa:
            self.mapa.atualizar()

    def on_telemetria(self, p, tempo_sessao):
        for i, tc in enumerate(p.m_carTelemetryData or []):
            if i < len(self.carros):
                self.carros[i].vel = iv(tc.m_speed)
        t = p.m_carTelemetryData[self.jogador]
        self.telemetria = t
        if self.pausado or self.eu.status_piloto == 0:
            return
        a = self.acum
        a["amostras"] += 1
        a["acel_soma"] += float(t.m_throttle)
        a["acel_cheio"] += 1 if t.m_throttle >= 0.98 else 0
        a["freio"] += 1 if t.m_brake >= 0.05 else 0
        if iv(t.m_speed) > a["vel_max"]:
            a["vel_max"] = iv(t.m_speed)
            if self.eu.x is not None:
                a["vel_max_xy"] = (self.eu.x, self.eu.z)
        superf = [iv(x) for x in t.m_surfaceType]
        a["fora_pista"] += 1 if sum(1 for x in superf if x not in (0, 1)) >= 2 else 0
        a["temp_tras"].append((iv(t.m_tyresSurfaceTemperature[0]) + iv(t.m_tyresSurfaceTemperature[1])) / 2)
        for k in range(4):
            if iv(t.m_tyresSurfaceTemperature[k]) >= 125:
                a["quente"][k] += 1
        dist = getattr(self, "_dist", -1.0)
        if dist >= 0 and len(self.amostras_volta) < 6000:
            self.amostras_volta.append((round(dist, 1), self.tempo_volta_atual, iv(t.m_speed),
                                        round(float(t.m_throttle), 2), round(float(t.m_brake), 2), iv(t.m_gear),
                                        round(self.eu.x or 0, 1), round(self.eu.z or 0, 1)))

        taxa = max(1, int(self.cfg.get("taxa_gravacao_hz", 10)))
        if tempo_sessao - self._ultima_tele < 1.0 / taxa - 1e-6:
            return
        self._ultima_tele = tempo_sessao
        eu = self.eu
        linha = {
            "tempo_sessao": round(tempo_sessao, 3), "volta": self.volta_atual,
            "dist_volta_m": round(getattr(self, "_dist", 0.0), 1), "setor": getattr(self, "_setor", 0) + 1,
            "velocidade_kmh": iv(t.m_speed), "acelerador": round(float(t.m_throttle), 3),
            "freio": round(float(t.m_brake), 3), "volante": round(float(t.m_steer), 3),
            "marcha": iv(t.m_gear), "rpm": iv(t.m_engineRPM), "drs": iv(t.m_drs),
            "ers_modo": self.ers_modo, "ers_bateria_mj": round(self.ers / 1e6, 3),
            "combustivel_kg": round(self.combustivel, 3), "comb_sobra_voltas": round(self.comb_sobra_voltas, 2),
            "pneu": PNEU_VISUAL.get(eu.pneu, eu.pneu), "idade_pneu": eu.idade_pneu,
            "posicao": eu.posicao, "dif_frente_s": round(eu.dif_frente_ms / 1000, 3),
            "dif_lider_s": round(getattr(self, "_dif_lider", 0) / 1000, 3),
            "pit_status": getattr(self, "_pit_status", 0), "volta_invalida": int(eu.invalida),
        }
        for k, r in enumerate(RODAS_COL):
            linha[f"desgaste_{r}"] = round(eu.desgaste[k], 2)
            linha[f"temp_sup_{r}"] = iv(t.m_tyresSurfaceTemperature[k])
            linha[f"temp_int_{r}"] = iv(t.m_tyresInnerTemperature[k])
            linha[f"temp_freio_{r}"] = iv(t.m_brakesTemperature[k])
            linha[f"pressao_{r}"] = round(float(t.m_tyresPressure[k]), 2)
            linha[f"superficie_{r}"] = superf[k]
        self._escrever("telemetria", linha)

    def on_voltas(self, p):
        if getattr(self, "_precisa_resumo", False):   # resumo sempre atualizado (se a janela for fechada no X)
            self._precisa_resumo = False
            self.escrever_resumo()
        lista = p.m_lapData or []
        for i, ld in enumerate(lista):
            if i >= len(self.carros):
                break
            c = self.carros[i]
            c.pos_ant = c.posicao
            c.posicao = iv(ld.m_carPosition)
            c.status_resultado = iv(ld.m_resultStatus)
            c.status_piloto = iv(ld.m_driverStatus)
            c.dif_frente_ms = iv(ld.m_deltaToCarInFrontInMS) + 60000 * iv(getattr(ld, "m_deltaToCarInFrontMinutes", 0))
            c.dif_lider_ms = iv(ld.m_deltaToRaceLeaderInMS) + 60000 * iv(getattr(ld, "m_deltaToRaceLeaderMinutes", 0))
            dist_ant = c.dist_volta
            c.dist_volta = float(ld.m_lapDistance)
            self._guardar_dist(i, float(getattr(ld, "m_totalDistance", 0) or 0))
            c.pit_status = iv(ld.m_pitStatus)
            c.paradas = iv(ld.m_numPitStops)
            volta = iv(ld.m_currentLapNum)
            s1 = iv(ld.m_sector1TimeInMS) + 60000 * iv(getattr(ld, "m_sector1TimeMinutes", 0))
            s2 = iv(ld.m_sector2TimeInMS) + 60000 * iv(getattr(ld, "m_sector2TimeMinutes", 0))
            setor = iv(ld.m_sector)
            c.setor = setor
            if volta > c.volta and c.volta > 0:
                self._volta_completa_carro(i, c, iv(ld.m_lastLapTimeInMS))
            elif volta < c.volta:  # flashback / reinício
                c.invalida = c.teve_pit = False
                c.s1 = c.s2 = 0
                if i == self.jogador:
                    self._flashback(volta)
            if volta != c.volta:
                c.volta = volta
                c.s1 = c.s2 = 0
                c.invalida = False
                c.teve_pit = False
            elif (self.comprimento_pista > 500 and dist_ant > self.comprimento_pista - 300
                  and 0 <= c.dist_volta < 300 and not iv(ld.m_pitStatus) and c.teve_pit):
                # cruzou a linha sem o número da volta mudar (saída da garagem no treino):
                # a volta lançada começa aqui, sem herdar o "pit" da volta de saída
                c.s1 = c.s2 = 0
                c.invalida = False
                c.teve_pit = False
                if i == self.jogador:
                    self.acum = self._novo_acum()
                    self.acum["comb_ini"] = self.combustivel
                    self.acum["desg_ini"] = max(self.eu.desgaste)
                    self.tipo_volta = set()
                    self.traco_atual = []
                    self.amostras_volta = []
            if setor >= 1 and s1 > 0:
                c.s1 = s1
            if setor >= 2 and s2 > 0:
                c.s2 = s2
            if iv(ld.m_currentLapInvalid):
                c.invalida = True
            if iv(ld.m_pitStatus):
                c.teve_pit = True

        if self.jogador >= len(lista):
            return
        ld = lista[self.jogador]
        eu = self.eu
        self._dist = float(ld.m_lapDistance)
        self.tempo_volta_atual = iv(ld.m_currentLapTimeInMS)
        self._setor = iv(ld.m_sector)
        self._atualizar_delta()
        if self.eh_corrida and self.av.get("pits_dos_rivais", True):
            self._regra_pits_rivais()
        if self.eh_corrida:
            self.vigia.tick()
        self._pit_status = iv(ld.m_pitStatus)
        self._dif_lider = iv(ld.m_deltaToRaceLeaderInMS) + 60000 * iv(getattr(ld, "m_deltaToRaceLeaderMinutes", 0))
        self.paradas = iv(ld.m_numPitStops)
        self.posicao = eu.posicao
        if not self.posicao_largada and iv(getattr(ld, "m_gridPosition", 0)):
            self.posicao_largada = iv(ld.m_gridPosition)
        if eu.status_piloto:
            self.tipo_volta.add(eu.status_piloto)
        if self._pit_status:
            self.acum["pit"] = True
        if self.safety_car in (1, 2):
            self.acum["sc"] = True

        # volta invalidada na classificação
        if not self.eh_corrida and eu.invalida and eu.status_piloto == 1:
            self.falar(tr("Volta invalidada.", "Lap invalidated."), 2, f"invalida-{eu.volta}", 9999)

        if self.av["penalidades"]:
            self._regra_penalidades(ld)
        if self.eh_corrida:
            if self.posicao_largada and "largada" not in self.avisos_feitos and eu.volta <= 1:
                self.avisos_feitos.add("largada")
                self.falar(falas.largada(self.posicao_largada, self.pista, self.total_voltas), 1, "largada-msg")
            self._regra_posicao()
            self._regra_carro_tras()
            self._regra_bandeirada()
        self.volta_atual = eu.volta

    def on_evento(self, p):
        cod = getattr(p, "m_eventStringCode", "")
        det = getattr(p, "mEventDetails", None)
        if cod == "FTLP" and det is not None:
            self.dono_volta_rapida = iv(getattr(det, "vehicleIdx", -1))
        if cod == "OVTK" and det is not None:
            a = iv(getattr(det, "overtakingVehicleIdx", -1))
            b = iv(getattr(det, "beingOvertakenVehicleIdx", -1))
            self.viu_ovtk = True
            if self.jogador in (a, b):
                agora = time.monotonic()
                self.ultrapassagens = [u for u in self.ultrapassagens if agora - u[0] < 30] + [(agora, a, b)]
        if cod == "LGOT":
            self._t_luzes = time.monotonic()
        if cod == "RTMT" and det is not None:
            motivo = getattr(det, "m_reason", 0)
            self.vigia.abandono(iv(getattr(det, "vehicleIdx", -1)), iv(getattr(motivo, "value", motivo)))
        if cod == "COLL" and det is not None:
            self.vigia.colisao(iv(getattr(det, "m_vehicle_1_index", -1)), iv(getattr(det, "m_vehicle_2_index", -1)))
        if cod == "LGOT" and self.eh_corrida:
            self.falar(tr(falas.escolher("Luzes apagadas! Vai, vai, vai!", "Luzes apagadas! Boa largada!"),
                          falas.escolher("Lights out! Go, go, go!", "Lights out! Good start!")), 2, "lgot", 60)
        if cod == "FTLP" and det is not None and iv(getattr(det, "vehicleIdx", -1)) == self.jogador and self.eh_corrida:
            self.falar(tr("Volta mais rápida da corrida! Boa!", "Fastest lap of the race! Nice!"), 1, "ftlp", 30)
            self.evento(tr("Volta mais rápida", "Fastest lap"))
        elif cod == "SCAR" and det is not None and self.av["safety_car"]:
            tipo = iv(getattr(det, "m_safety_car_type", 0))
            ev = iv(getattr(det, "m_event_type", 0))
            nome = tr("Safety Car virtual", "Virtual Safety Car") if tipo == 2 else "Safety Car"
            if ev == 1:
                self.falar(tr(f"{nome} entrando nesta volta. Prepare a relargada e aqueça os pneus.",
                              f"{nome} coming in this lap. Get ready for the restart and warm the tyres."), 2, "sc-volta", 30)
                self.evento(tr(f"{nome} recolhendo", f"{nome} ending"))
        elif cod == "BUTN" and det is not None:
            self._botoes(iv(getattr(det, "buttonStatus", 0)))
        elif cod == "CHQF":
            self.evento(tr("Bandeira quadriculada", "Chequered flag"))
            if self.eh_classif:
                self._fim_classificacao()
        elif cod == "SEND":
            self.evento(tr("Fim da sessão", "Session ended"))
            if self.eh_classif:
                self._fim_classificacao()
            self.escrever_resumo()
            self._salvar_historico_acerto()
            self._gerar_relatorio()
            self._analise_final(falar=True)
        elif cod == "RDFL":
            self.falar(tr("Bandeira vermelha. Volte devagar para os boxes.", "Red flag. Slowly back to the pits."), 3, "rdfl", 30)
            self.evento(tr("Bandeira vermelha", "Red flag"))
        elif cod == "PENA" and det is not None and iv(getattr(det, "vehicleIdx", -1)) == self.jogador:
            self.evento(tr("Penalidade", "Penalty") + f" {iv(getattr(det, 'penaltyType', -1))}, "
                        + tr("infração", "infringement") + f" {iv(getattr(det, 'infringementType', -1))}, "
                        + tr("tempo", "time") + f" {iv(getattr(det, 'time', 0))}s")

    # ---------------- volta completa ----------------
    def _volta_completa_carro(self, i, c, ultima_ms):
        if ultima_ms <= 0:
            return
        valida = not c.invalida
        s3 = ultima_ms - c.s1 - c.s2 if c.s1 and c.s2 else 0
        c.ultima_ms = ultima_ms
        c.ultima_volta_num = c.volta
        c.ultima_valida = valida
        c.ultima_teve_pit = c.teve_pit
        if valida and (not c.melhor_ms or ultima_ms < c.melhor_ms):
            c.melhor_ms = ultima_ms
        if valida and not c.teve_pit and c.s1 and c.s2 and s3 > 0:
            for k, v in enumerate([c.s1, c.s2, s3, ultima_ms]):
                if not self.melhores_sessao[k] or v < self.melhores_sessao[k]:
                    self.melhores_sessao[k] = v
        self._escrever("voltas_todos", {
            "volta": c.volta, "carro": i, "piloto": c.nome, "tempo": tempo_txt(ultima_ms),
            "tempo_ms": ultima_ms, "s1_ms": c.s1, "s2_ms": c.s2, "s3_ms": s3, "valida": int(valida),
            "teve_pit": int(c.teve_pit), "pneu": PNEU_VISUAL.get(c.pneu, c.pneu), "idade_pneu": c.idade_pneu,
            "posicao": c.posicao})
        if i == self.jogador:
            self._volta_completa_jogador(c, ultima_ms, valida, s3)
            if self.eh_corrida:
                self.vigia.fim_volta_jogador()
        elif self.eh_corrida:
            self.vigia.volta_carro(c, ultima_ms, c.s1, c.s2, s3)
        elif self.eh_classif and self.av["classificacao_zona_de_corte"]:
            self._regra_corte(apos_minha_volta=False)

    def _volta_completa_jogador(self, c, ms, valida, s3):
        a = self.acum
        antiga = (getattr(self, "_fb_descartadas", None) or {}).pop(c.volta, None)
        parcial = getattr(self, "_acum_parcial", False)
        self._acum_parcial = False
        if antiga is not None and antiga["tempo_ms"] == ms:
            # flashback para o fim desta volta e ela terminou igual: é a mesma volta de antes
            self.voltas.append(antiga)
            tr_ant = (getattr(self, "_fb_tracos", None) or {}).pop(c.volta, None)
            if tr_ant:
                self.tracos[c.volta] = tr_ant
            if not antiga["teve_pit"]:
                self.stint_desgaste_voltas.append(antiga["desgaste_max_fim"])
            self._precisa_resumo = True
            self.traco_atual = []
            self.amostras_volta = []
            self._ult_setor = 0
            return
        if (self.mapa is not None and valida and not (c.teve_pit or a["pit"]) and a.get("vel_max_xy")
                and a["amostras"] > 200):
            self.mapa.marcar_speed_trap(*a["vel_max_xy"], a["vel_max"])
        n = max(1, a["amostras"])
        desg_fim = max(c.desgaste)
        desg_volta = desg_fim - a["desg_ini"] if a["desg_ini"] is not None else 0
        consumo = (a["comb_ini"] - self.combustivel) if a["comb_ini"] is not None else 0
        tipo = "rápida" if 1 in self.tipo_volta else ("saída" if 3 in self.tipo_volta else
                                                       ("entrada" if 2 in self.tipo_volta else "normal"))
        if self.eh_corrida:
            tipo = "safety car" if a["sc"] else "corrida"
        teve_pit = bool(c.teve_pit or a["pit"])
        temp_tras = statistics.mean(a["temp_tras"]) if a["temp_tras"] else 0
        linha = {
            "volta": c.volta, "tempo": tempo_txt(ms), "tempo_ms": ms, "s1_ms": c.s1, "s2_ms": c.s2, "s3_ms": s3,
            "valida": int(valida), "tipo": tipo, "teve_pit": int(teve_pit),
            "pneu": PNEU_VISUAL.get(c.pneu, c.pneu), "idade_pneu": c.idade_pneu, "posicao": c.posicao,
            "desgaste_max_fim": round(desg_fim, 1), "desgaste_na_volta": round(desg_volta, 2),
            "combustivel_fim_kg": round(self.combustivel, 2), "consumo_volta_kg": round(consumo, 3),
            "vel_max_kmh": a["vel_max"], "acel_media_pct": round(100 * a["acel_soma"] / n, 1),
            "acel_cheio_pct": round(100 * a["acel_cheio"] / n, 1), "freio_pct": round(100 * a["freio"] / n, 1),
            "fora_pista_pct": round(100 * a["fora_pista"] / n, 1), "temp_sup_tras_media": round(temp_tras, 1),
            "clima": CLIMA.get(self.clima, self.clima), "temp_pista": self.temp_pista,
        }
        if parcial:
            # depois de um flashback a medição não cobriu a volta inteira: usa o começo da volta original
            if antiga is not None:
                linha["desgaste_na_volta"] = round(desg_fim - (antiga["desgaste_max_fim"] - antiga["desgaste_na_volta"]), 2)
                linha["consumo_volta_kg"] = round(antiga["combustivel_fim_kg"] + antiga["consumo_volta_kg"]
                                                  - self.combustivel, 3)
            else:
                linha["desgaste_na_volta"] = -1
                linha["consumo_volta_kg"] = -1
        self.voltas.append(linha)
        self._escrever("voltas", linha)
        self._precisa_resumo = True
        print(f"   Volta {c.volta:>2}: {tempo_txt(ms):>9}  S1 {tempo_txt(c.s1):>7}  S2 {tempo_txt(c.s2):>7}  "
              f"S3 {tempo_txt(s3):>7}  {'válida' if valida else 'INVÁLIDA'}  P{c.posicao}  "
              f"pneu {PNEU_VISUAL.get(c.pneu, '?')} {desg_fim:.0f}%  comb {self.combustivel:.1f} kg", flush=True)

        if not teve_pit:
            self.stint_desgaste_voltas.append(desg_fim)

        # recordes pessoais (voltas com pit não contam)
        limpa = valida and not teve_pit and c.s1 > 0 and c.s2 > 0 and s3 > 0
        melhorou = False
        if limpa and (not self.melhor_ms or ms < self.melhor_ms):
            melhorou = bool(self.melhor_ms)
            self.melhor_ms = ms
        perdas = []
        if limpa:
            for k, st in enumerate([c.s1, c.s2, s3]):
                if st > 0:
                    if self.melhor_setores[k] and st > self.melhor_setores[k]:
                        perdas.append((st - self.melhor_setores[k], k + 1))
                    if not self.melhor_setores[k] or st < self.melhor_setores[k]:
                        self.melhor_setores[k] = st

        # --- avisos ---
        falar_tempo = (self.av["tempo_de_volta_corrida"] if self.eh_corrida
                       else self.av["tempo_de_volta_treino_classificacao"] and tipo == "rápida")
        if falar_tempo and valida:  # volta inválida já foi avisada na hora
            dif = (ms - self.melhor_ms) / 1000 if self.melhor_ms else 0
            if melhorou or len([v for v in self.voltas if v["valida"]]) == 1:
                self.falar(tr(f"{tempo_fala(ms)}. Melhor volta pessoal.", f"{tempo_fala(ms)}. Personal best."), 1, "tempo-volta")
            elif dif < 0.05:
                self.falar(tr(f"{tempo_fala(ms)}. Igualou a sua melhor volta.", f"{tempo_fala(ms)}. Matched your best lap."),
                           1, "tempo-volta")
            else:
                txt = tr(f"{tempo_fala(ms)}. {falas.dif(dif)} mais lento que a sua melhor.",
                         f"{tempo_fala(ms)}. {falas.dif(dif)} off your best.")
                if perdas:
                    perda, setor = max(perdas)
                    if perda >= 100:
                        txt += tr(f" Perdeu mais no setor {setor}.", f" Most of it in sector {setor}.")
                self.falar(txt, 1, "tempo-volta")
        elif falar_tempo and self.eh_corrida:
            self.falar(tr(f"{tempo_fala(ms)}. Volta invalidada.", f"{tempo_fala(ms)}. Lap invalidated."), 1, "tempo-volta")

        if self.eh_classif and self.av["classificacao_zona_de_corte"]:
            self._regra_corte(apos_minha_volta=True)

        if self.eh_corrida:
            self._regras_fim_de_volta_corrida(c)

        if self.av["comparar_pneus_chuva_seco"] and (self.eh_corrida or self.eh_classif):
            self._regra_ritmo_pneus(c)

        if self.eh_corrida and melhorou and c.volta > 2:
            self.falar(tr(falas.escolher(f"Melhor volta pessoal, {tempo_fala(ms)}. Ritmo forte!",
                                         f"{tempo_fala(ms)}, sua melhor volta. Continue assim."),
                          falas.escolher(f"Personal best, {tempo_fala(ms)}. Strong pace!",
                                         f"{tempo_fala(ms)}, your best lap. Keep it up.")), 0, "pb-corrida", 120)
        if a["amostras"] > 200 and not teve_pit:
            fracs = [q / a["amostras"] for q in a["quente"]]
            k = fracs.index(max(fracs))
            if fracs[k] >= 0.08:
                if k == 2:
                    txt = tr("Dianteiro esquerdo superaquecendo. Alivie a frente nas curvas para a direita: "
                             "menos volante e acelerador progressivo.",
                             "Front left overheating. Go easier on the front in the right-handers: "
                             "less steering and a progressive throttle.")
                elif k == 3:
                    txt = tr("Dianteiro direito superaquecendo. Alivie a frente nas curvas para a esquerda: "
                             "menos volante e acelerador progressivo.",
                             "Front right overheating. Go easier on the front in the left-handers: "
                             "less steering and a progressive throttle.")
                else:
                    txt = tr("Traseiros superaquecendo. Acelere mais suave na saída das curvas lentas.",
                             "Rears overheating. Smoother on the throttle out of the slow corners.")
                self.falar(txt, 1, "pneu-quente", 300)

        lim = self.av.get("temperatura_pneu_alta_celsius") or 0
        if lim and temp_tras > lim:
            self.falar(tr(f"Pneus traseiros quentes, média de {temp_tras:.0f} graus. Alivie a aceleração na saída das curvas.",
                          f"Rear tyres hot, {temp_tras:.0f} degrees on average. Ease the throttle on corner exit."),
                       1, "temp-pneu", 180)

        if self.amostras_volta:
            comparavel = bool(limpa) and tipo not in ("safety car", "saída", "entrada") and not (
                self.eh_corrida and c.volta == 1)
            self.tracos[c.volta] = {"tempo": ms, "valida": bool(limpa), "comparavel": comparavel, "tipo": tipo,
                                    "pneu": linha["pneu"], "amostras": self.amostras_volta}
        if limpa and len(self.traco_atual) > 20 and (melhorou or self.traco_ref is None or ms <= self.melhor_ms):
            self.traco_ref = ([d for d, _ in self.traco_atual], [t for _, t in self.traco_atual])
        self.traco_atual = []
        self.amostras_volta = []
        self._ult_setor = 0

        self.acum = self._novo_acum()
        self.acum["comb_ini"] = self.combustivel
        self.acum["desg_ini"] = desg_fim
        self.tipo_volta = set()
        if "telemetria" in self._arq:
            self._arq["telemetria"].flush()

    # ---------------- delta ao vivo ----------------
    def _atualizar_delta(self):
        d, t = getattr(self, "_dist", -1.0), self.tempo_volta_atual
        if d < 0 or t <= 0 or self.eu.status_piloto not in (1, 4):
            self.delta_ms = None
            if self.eu.status_piloto in (0, 2, 3):
                self.traco_atual = []
            return
        if not self.traco_atual or d - self.traco_atual[-1][0] >= 5:
            if not self.traco_atual or d > self.traco_atual[-1][0]:
                self.traco_atual.append((d, t))
        ref = self.traco_ref
        if not ref or len(ref[0]) < 20:
            self.delta_ms = None
            return
        ds, ts = ref
        k = bisect.bisect_left(ds, d)
        if k <= 0 or k >= len(ds):
            self.delta_ms = None
            return
        f = (d - ds[k - 1]) / max(0.001, ds[k] - ds[k - 1])
        t_ref = ts[k - 1] + f * (ts[k] - ts[k - 1])
        self.delta_ms = int(t - t_ref)
        if self.acum.get("pit") or abs(self.delta_ms) > 15000:
            self.delta_ms = None
            return
        # aviso por setor (classificação/treino, volta rápida)
        setor = getattr(self, "_setor", 0)
        if (setor > self._ult_setor and not self.eh_corrida and self.eu.status_piloto == 1
                and self.av.get("delta_por_setor_classificacao", True) and not self.eu.invalida):
            dif = self.delta_ms / 1000
            if abs(dif) >= 0.1:
                txt = tr(f"Setor {setor}: {falas.dif(dif)} {'mais rápido' if dif < 0 else 'mais lento'}.",
                         f"Sector {setor}: {falas.dif(dif)} {'up' if dif < 0 else 'down'}.")
                self.falar(txt, 0, f"delta-setor-{self.eu.volta}-{setor}", 9999)
        self._ult_setor = setor

    # ---------------- rivais ----------------
    def _regra_pits_rivais(self):
        eu = self.eu
        if eu.volta <= 1 or not eu.posicao:
            return
        for c in self.carros:
            if c.idx == self.jogador or c.status_resultado != 2:
                continue
            if c.pit_status and c.idx not in self.rivais_no_pit:
                meu = eu.pos_ant or eu.posicao
                dele = c.pos_ant or c.posicao
                if dele in (meu - 1, meu + 1) and not self._pit_status:
                    lado = tr("na sua frente", "ahead of you") if dele < meu else tr("atrás de você", "behind you")
                    nome = self._nome(c.idx) or tr("O carro", "The car")
                    self.rivais_no_pit[c.idx] = (c.pneu, lado)
                    self.falar(tr(f"{nome}, {lado}, entrou nos boxes.", f"{nome}, {lado}, is pitting."), 1, f"pit-riv-{c.idx}", 30)
                    self.vigia.rival_entrou_box(c, atras=dele > meu)
                    self.evento(tr(f"{nome} ({lado}) entrou nos boxes", f"{nome} ({lado}) pitted"))
                else:
                    self.rivais_no_pit[c.idx] = None
            elif not c.pit_status and c.idx in self.rivais_no_pit:
                info = self.rivais_no_pit.pop(c.idx)
                if info:
                    nome = self._nome(c.idx) or tr("O carro", "The car")
                    pneu = PNEU_VISUAL.get(c.pneu, "")
                    self.falar(tr(f"{nome} saiu dos boxes{' de ' + pneu if pneu else ''}, em P{c.posicao}.",
                                  f"{nome} is out of the pits{' on ' + pneu + 's' if pneu else ''}, in P{c.posicao}."), 1,
                               f"pit-riv-saida-{c.idx}", 30)

    # ---------------- perguntas (botões do controle / painel) ----------------
    def _botoes(self, status):
        antes = getattr(self, "_botoes_antes", 0)
        novos = status & ~antes
        self._botoes_antes = status
        mapa = self.cfg.get("botoes_udp") or {}
        for n in range(1, 13):
            if novos & (0x00100000 << (n - 1)):
                acao = mapa.get(str(n))
                if acao:
                    self.perguntar(acao)

    def perguntar(self, tipo):
        agora = time.monotonic()
        if agora - getattr(self, "_ult_pergunta", {}).get(tipo, -9) < 1.5:
            return
        self._ult_pergunta = {**getattr(self, "_ult_pergunta", {}), tipo: agora}
        if tipo == "repetir":
            self.radio.repetir_ultima()
            return
        if tipo == "teste_radio":
            self.radio.teste_de_radio()
            return
        if tipo == "rivais":
            self.falar(self.vigia.briefing() if self.eh_corrida else
                       tr("A estratégia dos rivais eu acompanho na corrida.", "I track rival strategy during the race."),
                       2, None)
            return
        txt = {"situacao": self._resp_situacao, "pneus": self._resp_pneus,
               "estrategia": self._resp_estrategia, "combustivel": self._resp_combustivel,
               "clima": self._resp_clima, "pecas": self._resp_pecas}.get(tipo, lambda: "")()
        if txt:
            self.falar(txt, 2, None)

    def responder_livre(self, texto):
        import conversa
        try:
            return conversa.Conversa(self).responder(texto)
        except Exception as e:  # noqa: BLE001
            print(f"[CONVERSA] {e}")
            return None

    def _resp_situacao(self):
        eu = self.eu
        if not eu.posicao:
            return tr("Ainda sem dados da sua posição.", "No position data yet.")
        partes = [f"P{eu.posicao}."]
        if self.eh_corrida:
            if self.total_voltas:
                partes.append(tr(f"Volta {eu.volta} de {self.total_voltas}.", f"Lap {eu.volta} of {self.total_voltas}."))
            frente, gf = self.gap_frente()
            tras, gt = self.gap_tras()
            if frente is not None and gf:
                n = self._nome(frente.idx)
                partes.append(tr(f"Na frente{(', ' + n) if n else ''}, a {falas.gap(gf)}.",
                                 f"Ahead{(', ' + n) if n else ''}, {falas.gap(gf)}."))
            if tras is not None and gt:
                n = self._nome(tras.idx)
                partes.append(tr(f"Atrás{(', ' + n) if n else ''}, a {falas.gap(gt)}.",
                                 f"Behind{(', ' + n) if n else ''}, {falas.gap(gt)}."))
        else:
            if self.melhor_ms:
                partes.append(tr(f"Sua melhor volta: {tempo_fala(self.melhor_ms)}.", f"Your best lap: {tempo_fala(self.melhor_ms)}."))
            p1 = min((c.melhor_ms for c in self.carros if c.melhor_ms), default=0)
            if p1 and self.melhor_ms and self.melhor_ms > p1:
                d = falas.dif((self.melhor_ms - p1) / 1000)
                partes.append(tr(f"{d} para o primeiro.", f"{d} off P1."))
            if self.tempo_restante:
                m = self.tempo_restante // 60
                partes.append(tr(f"Faltam {m} minutos.", f"{m} minutes to go."))
        return " ".join(partes)

    def _resp_pneus(self):
        c = self.eu
        if not c.pneu:
            return tr("Ainda sem dados dos pneus.", "No tyre data yet.")
        desg = max(c.desgaste)
        pior = RODAS[c.desgaste.index(desg)]
        txt = tr(f"Pneus {PNEU_PLURAL.get(c.pneu, '')} com {c.idade_pneu} voltas, {desg:.0f} por cento de desgaste, "
                 f"o {pior} é o mais gasto.",
                 f"{PNEU_PLURAL.get(c.pneu, 'Tyres').capitalize()}, {c.idade_pneu} laps old, {desg:.0f} percent wear, "
                 f"the {pior} is the most worn.")
        faltam = self.total_voltas - max(0, c.volta - 1) if (self.eh_corrida and self.total_voltas) else 0
        ritmo = self._ritmo_desgaste()
        if faltam and ritmo and ritmo > 0.05:
            fim = desg + ritmo * faltam
            if fim <= 75:
                txt += tr(f" No ritmo atual, chegam ao fim com cerca de {fim:.0f} por cento.",
                          f" At this rate, they'll finish at about {fim:.0f} percent.")
            else:
                n = max(0, int((75 - desg) / ritmo))
                txt += tr(f" Chegam a 75 por cento em cerca de {n} voltas.", f" They'll hit 75 percent in about {n} laps.")
        if self.eh_corrida:
            s = self.comb_sobra_voltas
            txt += tr(f" Combustível: {'sobrando' if s >= 0 else 'faltando'} {falas.voltas(s)}.",
                      f" Fuel: {falas.voltas(s)} {'spare' if s >= 0 else 'short'}.")
        return txt

    def _resp_combustivel(self):
        if self.eh_corrida:
            s = self.comb_sobra_voltas
            if s < -0.2:
                return tr(f"Combustível curto: falta {falas.voltas(s)}. Tire o pé um pouco antes das freadas "
                          f"nas retas longas.",
                          f"Fuel is short by {falas.voltas(s)}. Lift a little before braking on the long straights.")
            return tr(f"Combustível ok, {'sobrando' if s >= 0 else 'faltando'} {falas.voltas(s)}. {self.combustivel:.0f} quilos no tanque.",
                      f"Fuel is fine, {falas.voltas(s)} {'spare' if s >= 0 else 'short'}. {self.combustivel:.0f} kilos in the tank.")
        return tr(f"{self.combustivel:.0f} quilos de combustível no tanque.", f"{self.combustivel:.0f} kilos of fuel in the tank.")

    def _resp_pecas(self):
        if not self.pecas:
            return tr("Ainda não recebi os dados das peças.", "No parts data yet.")
        ordem = sorted(((v, falado) for attr, nome, falado in self.NOMES_PECAS
                        for k, v in self.pecas.items() if k == nome), reverse=True)
        txt = tr("Peças: ", "Parts: ") + ", ".join(tr(f"{falado} com {v} por cento", f"{falado} at {v} percent")
                                                  for v, falado in ordem[:3]) + "."
        if ordem and ordem[0][0] >= 70:
            txt += tr(f" Recomendo trocar {ordem[0][1]} depois desta sessão.", f" I'd swap {ordem[0][1]} after this session.")
        return txt

    def _resp_clima(self):
        txt = tr(f"Agora: {CLIMA.get(self.clima, '')}, pista a {self.temp_pista} graus.",
                 f"Now: {CLIMA.get(self.clima, '')}, track at {self.temp_pista} degrees.")
        if self.duracao and self.previsao:
            decorrido = (self.duracao - self.tempo_restante) / 60
            molhado = self.clima >= 3
            prox = sorted((x for x in self.previsao if x[0] == self.tipo and x[1] > decorrido), key=lambda x: x[1])
            mud = next((x for x in prox if (x[2] >= 3) != molhado), None)
            if mud:
                faltam = max(1, round(mud[1] - decorrido))
                if mud[2] >= 3:
                    txt += tr(f" Previsão de {CLIMA.get(mud[2])} em cerca de {faltam} minutos, {mud[3]} por cento de chance.",
                              f" {CLIMA.get(mud[2]).capitalize()} forecast in about {faltam} minutes, {mud[3]} percent chance.")
                else:
                    txt += tr(f" A chuva deve parar em cerca de {faltam} minutos.", f" The rain should stop in about {faltam} minutes.")
            else:
                txt += tr(" Sem mudança prevista nesta sessão.", " No change expected this session.")
        return txt

    def _resp_estrategia(self):
        if not self.eh_corrida:
            return tr("Estratégia de parada só vale na corrida. Foque em voltas limpas.",
                      "Pit strategy only matters in the race. Focus on clean laps.")
        c = self.eu
        faltam = self.total_voltas - max(0, c.volta - 1) if self.total_voltas else 0
        partes = []
        if self.rejoin:
            outros = sorted((o for o in self.carros if o.idx != self.jogador and o.status_resultado == 2
                             and o.posicao), key=lambda o: o.posicao)
            atras_de = outros[self.rejoin - 2] if 2 <= self.rejoin <= len(outros) + 1 else None
            nome = self._nome(atras_de.idx) if atras_de is not None else ""
            partes.append(tr(f"Se parar agora, volta em P{self.rejoin}{(', atrás de ' + nome) if nome else ''}.",
                             f"If you pit now, you rejoin in P{self.rejoin}{(', behind ' + nome) if nome else ''}."))
        desg = max(c.desgaste)
        ritmo = self._ritmo_desgaste()
        r = self.calcular_plano(self.safety_car if self.safety_car in (1, 2) else 0)
        if r:
            partes.append(self._texto_plano(*r))
            ritmo = None
        if faltam and ritmo and ritmo > 0.05:
            fim = desg + ritmo * faltam
            if fim <= 75:
                partes.append(tr(f"Os pneus aguentam até o fim, cerca de {fim:.0f} por cento.",
                                 f"The tyres can make the end, at about {fim:.0f} percent."))
            else:
                voltas = max(0, int((75 - desg) / ritmo))
                partes.append(tr(f"Os pneus chegam a 75 por cento em cerca de {voltas} voltas.",
                                 f"The tyres hit 75 percent in about {voltas} laps."))
        if self.paradas == 0 and self.pit_ideal > 0:
            partes.append(tr(f"Estratégia do jogo: parar na volta {self.pit_ideal}.",
                             f"The game's strategy: pit on lap {self.pit_ideal}."))
        if self.safety_car in (1, 2):
            partes.append(tr("Com Safety Car, a parada sai barata.", "Under the Safety Car, a stop is cheap."))
        if not partes or (len(partes) == 1 and self.safety_car in (1, 2)):
            partes.insert(0, tr(f"Pneus com {desg:.0f} por cento de desgaste e {c.idade_pneu} voltas. "
                                f"Ainda não tenho voltas suficientes deste jogo de pneus para projetar o desgaste.",
                                f"Tyres at {desg:.0f} percent wear after {c.idade_pneu} laps. "
                                f"Not enough laps on this set yet to project the wear."))
        return " ".join(partes)

    # ---------------- memória de acertos ----------------
    ARQ_HIST = os.path.join(AQUI, "historico_acertos.json")

    def _ler_historico(self):
        try:
            with open(self.ARQ_HIST, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    def _clima_tipo(self):
        if not self.voltas:
            return "chuva" if self.clima >= 3 else "seco"
        molhadas = sum(1 for v in self.voltas if any(p in str(v.get("clima", "")).lower()
                                                     for p in ("chuva", "tempestade", "rain", "storm")))
        return "chuva" if molhadas >= len(self.voltas) / 2 else "seco"

    def _lembrar_acerto(self):
        if self.cfg.get("_demo"):
            return
        hist = [h for h in self._ler_historico() if h.get("pista") == self.pista]
        if not hist:
            return
        clima = "chuva" if self.clima >= 3 else "seco"
        mesmos = [h for h in hist if h.get("clima") == clima] or hist
        corridas = [h for h in mesmos if h.get("corrida") and h.get("posicao")]
        if corridas:
            h = min(corridas, key=lambda x: (x["posicao"], -len(x.get("data", ""))))
            resultado = tr("venceu", "won") if h["posicao"] == 1 else tr(f"terminou em P{h['posicao']}", f"finished P{h['posicao']}")
        else:
            h = mesmos[-1]
            mv = str(h.get("melhor_volta") or "")
            try:     # "1:14.400" -> falado ("1 minuto 14 vírgula 4" / "1 minute 14 point 4")
                m_, _, s_ = mv.rpartition(":")
                mv = falas.tempo(round((int(m_ or 0) * 60 + float(s_)) * 1000))
            except ValueError:
                pass
            resultado = (tr(f"fez {mv}", f"did a {mv}") if mv else tr("andou", "ran"))
        a = h.get("acerto") or {}
        if not a:
            return
        quando = tr("na chuva", "in the wet") if h.get("clima") == "chuva" else tr("no seco", "in the dry")
        fw, rw, dif = f"{a.get('frontWing', 0):.0f}", f"{a.get('rearWing', 0):.0f}", f"{a.get('onThrottle', 0):.0f}"
        self.falar(tr(f"Da última vez em {self.nome_pista} {quando}, você {resultado} com asa "
                      f"{fw} na frente e {rw} atrás, diferencial {dif} por cento.",
                      f"Last time at {self.nome_pista} {quando}, you {resultado} with front wing {fw}, "
                      f"rear wing {rw} and {dif} percent differential."), 0, "lembrar-acerto", 9999)
        self.evento(tr(f"Acerto anterior lembrado ({h.get('data', '')[:10]})", f"Previous setup recalled ({h.get('data', '')[:10]})"))

    def _salvar_historico_acerto(self):
        if self.cfg.get("_demo"):
            return
        if not self.acertos or not self.voltas or getattr(self, "_hist_salvo", False):
            return
        self._hist_salvo = True
        validas = [v for v in self.voltas if v["valida"] and not v["teve_pit"]]
        melhor = min(validas, key=lambda v: v["tempo_ms"]) if validas else None
        entrada = {"data": self.inicio.isoformat(timespec="minutes"), "pista": self.pista,
                   "pista_nome": self.nome_pista, "sessao": self.nome_sessao, "corrida": self.eh_corrida,
                   "clima": self._clima_tipo(), "acerto": self.acertos[-1][1],
                   "melhor_volta": melhor["tempo"] if melhor else "",
                   "posicao": (self.posicao_final or self.posicao) if self.eh_corrida else self.posicao}
        hist = self._ler_historico()
        hist.append(entrada)
        try:
            with open(self.ARQ_HIST, "w", encoding="utf-8") as f:
                json.dump(hist[-300:], f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    # ---------------- relatório ----------------
    def _analise_final(self, falar=True):
        """Fim de treino: análise automática (ritmo, pneus, acerto, plano da corrida) em analise.txt."""
        if getattr(self, "_analise_ok", False) or not self.pasta or self.tipo not in SESSOES_TREINO:
            return
        if len([v for v in self.voltas if v.get("valida") and not v.get("teve_pit")]) < 2:
            return
        self._analise_ok = True
        for a in self._arq.values():
            try:
                a.flush()
            except OSError:
                pass
        try:
            import analise
            r = analise.analisar(self.pasta, self.pista, self.comprimento_pista,
                                 int(self.cfg.get("distancia_corrida_pct", 50) or 50), self.eu.nome, self.nome_pista)
            with open(os.path.join(self.pasta, "analise.txt"), "w", encoding="utf-8") as f:
                f.write(r["texto"])
            self._salvar_hist_pneus(r["taxas"])
            print(f"[ANÁLISE] {os.path.join(self.pasta, 'analise.txt')}")
            if falar and r["falado"]:
                self.falar(tr("Análise do treino. ", "Practice debrief. ") + r["falado"], 1, "analise", 9999)
        except Exception as e:  # noqa: BLE001
            print(f"[ANÁLISE] Não consegui analisar a sessão: {e}")

    def _gerar_relatorio(self):
        if not self.pasta or getattr(self, "_relatorio_ok", False):
            return
        if not any(v["valida"] and len(v["amostras"]) > 50 for v in self.tracos.values()):
            return
        try:
            import relatorio
            caminho = relatorio.gerar(self, os.path.join(self.pasta, "relatorio.html"))
            self._relatorio_ok = True
            print(f"[RELATÓRIO] {caminho}")
        except Exception as e:  # noqa: BLE001
            print(f"[RELATÓRIO] Não consegui gerar o relatório: {e}")

    def _fim_classificacao(self):
        eu = self.eu
        melhor = eu.melhor_ms or self.melhor_ms
        if self.fim_quali_falado or not eu.posicao or not melhor:
            return
        self.fim_quali_falado = True
        melhores = sorted(c.melhor_ms for c in self.carros if c.melhor_ms > 0)
        pole = melhores[0] if melhores else 0
        if self.tipo in CORTE_Q1:
            n = self.n_carros_ativos or 22
            tipo, corte = "q1", n - max(1, (n - 10) // 2)
        elif self.tipo in CORTE_Q2:
            tipo, corte = "q2", 10
        else:
            tipo, corte = "final", 0
        dif_corte = (melhor - melhores[corte - 1]) / 1000 if corte and eu.posicao > corte and len(melhores) >= corte else 0
        dif_pole = (melhor - pole) / 1000 if pole else 0
        setor = None
        if all(self.melhor_setores) and all(self.melhores_sessao[:3]):
            perdas = [self.melhor_setores[k] - self.melhores_sessao[k] for k in range(3)]
            if max(perdas) > 50:
                setor = perdas.index(max(perdas)) + 1
        self.falar(falas.fim_classificacao(tipo, eu.posicao, self.n_carros_ativos, dif_pole, max(0, dif_corte),
                                           corte, setor), 2, "fim-quali", 9999)
        self.evento(tr(f"Fim da classificação: P{eu.posicao}", f"Qualifying finished: P{eu.posicao}"))

    def _licao_da_corrida(self):
        partes = []
        d = self.eu.desgaste
        if d and max(d) > 0:
            partes.append(tr(f"Para a próxima: o pneu que mais sofreu hoje foi o {RODAS[d.index(max(d))]}.",
                             f"For next time: the tyre that suffered most today was the {RODAS[d.index(max(d))]}."))
        passou = [v for i, v in enumerate(self.voltas[:-1])
                  if v["desgaste_max_fim"] >= 85 and self.voltas[i + 1]["teve_pit"]]
        if passou:
            partes.append(tr("Em um dos stints o pneu passou de 85 por cento antes da parada. "
                             "Parar uma ou duas voltas antes teria rendido mais.",
                             "In one stint the tyre went past 85 percent before the stop. "
                             "Pitting a lap or two earlier would have paid off."))
        partes.append(tr("O relatório da corrida mostra as curvas onde dá para ganhar tempo.",
                         "The race report shows the corners where you can find time."))
        return " ".join(partes)

    def _flashback(self, volta):
        """Flashback: descarta as voltas que serão refeitas (não duplicar no resumo/relatório)."""
        # guarda o que foi descartado: se o flashback foi para o finzinho da volta e ela terminar igual,
        # é a mesma volta (não grava de novo, não fala de novo, não perde o desgaste medido)
        self._fb_descartadas = {v["volta"]: v for v in self.voltas if v["volta"] >= volta}
        self._fb_tracos = {k: self.tracos[k] for k in self.tracos if k >= volta}
        self._acum_parcial = True
        self.voltas = [v for v in self.voltas if v["volta"] < volta]
        for k in [k for k in self.tracos if k >= volta]:
            self.tracos.pop(k, None)
        self.stint_desgaste_voltas = self.stint_desgaste_voltas[:max(0, volta - self.stint_inicio_volta)]
        self.traco_atual = []
        self.amostras_volta = []
        self.acum = self._novo_acum()
        self.evento(tr(f"Flashback para a volta {volta}", f"Flashback to lap {volta}"))

    # ---------------- estratégia calculada ----------------
    def on_conjuntos(self, p):
        if iv(getattr(p, "m_carIdx", self.jogador)) != self.jogador:
            return
        lista = []
        for k, t in enumerate(getattr(p, "m_tyreSetData", None) or []):
            lista.append({"comp": iv(t.m_visualTyreCompound), "desg": float(iv(t.m_wear)),
                          "disp": bool(iv(t.m_available)), "montado": bool(iv(t.m_fitted)),
                          "vida": iv(getattr(t, "m_usableLife", 0)), "delta": iv(getattr(t, "m_lapDeltaTime", 0))})
        self.conjuntos = lista

    def _hist_pneus(self):
        try:
            with open(os.path.join(AQUI, "historico_pneus.json"), encoding="utf-8") as f:
                return json.load(f).get(str(self.pista), {})
        except (OSError, ValueError):
            return {}

    def _salvar_hist_pneus(self, taxas):
        if not taxas or self.cfg.get("_demo"):
            return
        arq = os.path.join(AQUI, "historico_pneus.json")
        try:
            with open(arq, encoding="utf-8") as f:
                tudo = json.load(f)
        except (OSError, ValueError):
            tudo = {}
        atual = tudo.setdefault(str(self.pista), {})
        for c, t in taxas.items():
            atual[str(c)] = round(t, 3)
        try:
            with open(arq, "w", encoding="utf-8") as f:
                json.dump(tudo, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def calcular_plano(self, sc=0, feitas=None):
        """Melhor plano de paradas a partir de agora, com o desgaste real. Devolve (melhor, {paradas: plano}) ou None."""
        import estrategia as est
        c = self.eu
        if not self.eh_corrida or not self.total_voltas or c.pneu not in est.SECOS or self.clima >= 3:
            return None
        feitas = max(0, c.volta - 1) if feitas is None else feitas
        self._volta_em_andamento = feitas + 1
        restantes = self.total_voltas - feitas
        if restantes <= 1:
            return None
        medida = self._ritmo_desgaste()
        vida = {}
        for j in self.conjuntos:
            if j["comp"] in est.SECOS and j["vida"] > 0:
                vida[j["comp"]] = max(vida.get(j["comp"], 0), j["vida"])
        taxas = est.taxas_estimadas(c.pneu, medida, vida, self._hist_pneus(), est.FATOR_TANQUE_CHEIO)
        if not taxas.get(c.pneu):
            return None
        jogos = [(j["comp"], j["desg"]) for j in self.conjuntos
                 if j["disp"] and not j["montado"] and j["comp"] in est.SECOS]
        if not jogos:      # o jogo ainda não mandou os jogos: supõe um novo de cada composto seco
            jogos = [(k, 0.0) for k in est.SECOS]
        deltas = {}
        for j in self.conjuntos:
            if j["comp"] in est.SECOS and j["desg"] < 10 and j["delta"]:
                deltas.setdefault(j["comp"], j["delta"] / 1000)
        if deltas:          # o delta do jogo é em relação ao pneu montado; normaliza pelo médio
            ref = deltas.get(est.MEDIO, 0.0)
            deltas = {k: v - ref for k, v in deltas.items()}
        planos = est.planejar(restantes, c.pneu, max(c.desgaste), taxas, jogos, est.perda_box(self.pista, sc),
                              self.compostos_usados, deltas=deltas, total=self.total_voltas)
        if not planos:
            return None
        return planos[0], est.melhores_por_paradas(planos)

    def _texto_plano(self, melhor, por_paradas):
        import estrategia as est
        txt = est.descrever(melhor, getattr(self, "_volta_em_andamento", max(1, self.eu.volta)), 0)
        k = len(melhor["paradas"])
        outros = [(n, p) for n, p in por_paradas.items() if n != k]
        if outros:
            n, p = min(outros, key=lambda x: x[1]["tempo"])
            dif = p["tempo"] - melhor["tempo"]
            if dif >= 1:
                rot = tr({0: "sem parar", 1: "uma parada", 2: "duas paradas"}[n], {0: "no stop", 1: "one stop", 2: "two stops"}[n])
                txt += tr(f" É {falas.dif(dif)} mais rápido que {rot}.", f" That's {falas.dif(dif)} faster than {rot}.")
        return txt

    def _regra_plano(self, volta_concluida):
        """Depois de cada volta da corrida: avisa o plano quando ele muda e chama o box na hora certa."""
        if volta_concluida < 3 or self.safety_car in (1, 2):
            return
        r = self.calcular_plano(feitas=volta_concluida)
        if not r:
            return
        melhor, por = r
        self.plano = melhor
        if not melhor["paradas"]:
            if self.plano_anunciado != ("fim",):
                self.plano_anunciado = ("fim",)
                self.falar(tr("Os pneus aguentam até o fim, sem parar.", "The tyres can go to the end, no stop needed."), 1, "plano", 60)
            return
        s, comp = melhor["paradas"][0]
        volta_box = volta_concluida + s
        nome_comp = falas_pneu(comp)
        anunciado = self.plano_anunciado
        confirmado = bool(anunciado) and anunciado != ("fim",) and abs(anunciado[0] - volta_box) <= 1
        if s == 1 and confirmado:
            self.falar(tr(f"Box, box nesta volta para o {nome_comp}.", f"Box, box this lap for the {nome_comp}."), 2, "plano-box", 60)
        elif s == 2 and confirmado:
            self.falar(tr(f"Box na próxima volta. Vamos colocar o {nome_comp}.", f"Box next lap. We'll fit the {nome_comp}."),
                       1, "plano-box-prox", 60)
        mudou = (not anunciado or anunciado == ("fim",) or abs(anunciado[0] - volta_box) >= 2 or anunciado[1] != comp)
        if s > 2 and mudou and volta_concluida - self._plano_volta_falada >= 3:
            self.plano_anunciado = (volta_box, comp)
            self._plano_volta_falada = volta_concluida
            self.falar(tr("Pelo desgaste, o plano é: ", "Based on the wear, the plan is: ") + self._texto_plano(melhor, por),
                       1, "plano", 60)

    def _novo_stint(self):
        self.evento(tr(f"Troca de pneu: {PNEU_VISUAL.get(self.eu.pneu, '?')}", f"Tyre change: {PNEU_VISUAL.get(self.eu.pneu, '?')}"))
        self.acum["desg_ini"] = None   # pneu novo: o desgaste da volta conta a partir dele
        self.stint_inicio_volta = max(1, self.volta_atual)
        self.stint_desgaste_voltas = []
        self.alertas_desgaste_feitos = set()

    # ---------------- regras ----------------
    def _ritmo_desgaste(self):
        d = self.stint_desgaste_voltas
        if len(d) < 3:
            return None
        ult = d[-6:]
        difs = [b - a for a, b in zip(ult, ult[1:]) if b >= a]
        return statistics.mean(difs) if difs else None

    def _regras_fim_de_volta_corrida(self, c):
        volta_concluida = c.volta
        faltam = self.total_voltas - volta_concluida if self.total_voltas else 0
        try:
            self._regra_plano(volta_concluida)
        except Exception as e:  # noqa: BLE001
            print(f"[ESTRATÉGIA] {e}")

        # fim da 1ª volta
        if volta_concluida == 1:
            ganho = (self.posicao_largada - c.posicao) if self.posicao_largada else 0
            txt = tr(f"Fim da primeira volta. P{c.posicao}.", f"End of lap one. P{c.posicao}.")
            if ganho > 0:
                txt += tr(f" Ganhou {ganho} {'posição' if ganho == 1 else 'posições'}.",
                          f" {ganho} {'place' if ganho == 1 else 'places'} gained.")
            elif ganho < 0:
                txt += tr(f" Perdeu {-ganho} {'posição' if ganho == -1 else 'posições'}.",
                          f" {-ganho} {'place' if ganho == -1 else 'places'} lost.")
            self.falar(txt, 1, "volta1")
            self.pos_anunciada = c.posicao

        # posição e diferenças
        n = self.av["posicao_e_diferencas_a_cada_voltas"]
        if n and volta_concluida > 1 and volta_concluida % n == 0 and faltam > 0:
            partes = [f"P{c.posicao}."]
            frente, gf = self.gap_frente()
            tras, gt = self.gap_tras()
            if frente is not None and gf:
                nome = self._nome(frente.idx)
                partes.append(tr(f"Na frente{(', ' + nome) if nome else ''}, a {falas.gap(gf)}.",
                                 f"Ahead{(', ' + nome) if nome else ''}, {falas.gap(gf)}."))
            if tras is not None and gt:
                nome = self._nome(tras.idx)
                partes.append(tr(f"Atrás{(', ' + nome) if nome else ''}, a {falas.gap(gt)}.",
                                 f"Behind{(', ' + nome) if nome else ''}, {falas.gap(gt)}."))
            self.falar(" ".join(partes), 0, "gaps")

        # pneus
        desg = max(c.desgaste)
        for lim in sorted(self.av["desgaste_pneus_alertas"] or []):
            if desg >= lim and lim not in self.alertas_desgaste_feitos:
                self.alertas_desgaste_feitos.add(lim)
                pior = RODAS[c.desgaste.index(max(c.desgaste))]
                txt = tr(f"Pneus com {desg:.0f} por cento de desgaste, o {pior} é o mais gasto.",
                         f"Tyres at {desg:.0f} percent wear, the {pior} is the most worn.")
                ritmo = self._ritmo_desgaste()
                if ritmo and ritmo > 0.05 and faltam > 0:
                    fim = desg + ritmo * faltam
                    if fim <= 75:
                        txt += tr(f" No ritmo atual, chegam ao fim com cerca de {fim:.0f} por cento.",
                                  f" At this rate, they'll finish at about {fim:.0f} percent.")
                    else:
                        voltas_ate = int((75 - desg) / ritmo) if desg < 75 else 0
                        if voltas_ate <= 0:
                            txt += tr(" Já passaram do limite recomendado.", " They're already past the recommended limit.")
                        else:
                            txt += tr(f" Chegam a 75 por cento em cerca de {voltas_ate} voltas.",
                                      f" They'll hit 75 percent in about {voltas_ate} laps.")
                self.falar(txt, 2 if lim >= 70 else 1, f"desg-{lim}")

        # pneu no limite: box
        chave_box = f"box-limite-{self.stint_inicio_volta}"
        if desg >= 75 and faltam > 3 and chave_box not in self.avisos_feitos and not getattr(self, "_pit_status", 0):
            self.avisos_feitos.add(chave_box)
            self.falar(tr(f"Pneus no limite, {desg:.0f} por cento. Box, box nesta volta!",
                          f"Tyres are done, {desg:.0f} percent. Box, box this lap!"), 3, "box-limite", 30)

        # tendência das diferenças (ganhando ou perdendo para quem está perto)
        frente, gf = self.gap_frente()
        tras, gt = self.gap_tras()
        # paradas (minhas e dos dois vizinhos) junto: se alguém parou no meio, a "tendência" é falsa
        self.hist_gaps.append((volta_concluida, frente.idx if frente else -1, gf if frente is not None else None,
                               tras.idx if tras else -1, gt if tras is not None else None,
                               (self.eu.paradas, frente.paradas if frente else -1, tras.paradas if tras else -1,
                                bool(self.eu.teve_pit or self.eu.pit_status))))
        h = self.hist_gaps[-3:]
        sem_box = len(h) == 3 and len({x[5][:3] for x in h}) == 1 and not any(x[5][3] for x in h)
        if (len(h) == 3 and sem_box and volta_concluida > 2 and faltam > 1 and self.safety_car == 0
                and h[0][0] == volta_concluida - 2):
            if all(x[1] == h[-1][1] and x[2] for x in h):
                taxa, gap = (h[0][2] - h[-1][2]) / 2, h[-1][2]
                if 0.15 <= taxa <= 2.5 and gap < 6:
                    nome = self._nome(h[-1][1]) or tr("o carro da frente", "the car ahead")
                    voltas = max(1, round((gap - 0.8) / taxa))
                    txt = tr(f"Você está tirando {falas.dif(taxa)} por volta de {nome}, que está a {falas.gap(gap)}.",
                             f"You're catching {nome} by {falas.dif(taxa)} a lap, gap is {falas.gap(gap)}.")
                    txt += (tr(f" Alcança em cerca de {voltas} voltas.", f" You'll be on him in about {voltas} laps.") if gap > 1.2
                            else tr(f" Prepare o ataque {falas.ultrapassagem(self.pista)}.",
                                    f" Get ready to attack {falas.ultrapassagem(self.pista)}."))
                    self.falar(txt, 0, "tendencia-frente", 150)
            if all(x[3] == h[-1][3] and x[4] for x in h):
                taxa, gap = (h[0][4] - h[-1][4]) / 2, h[-1][4]
                if 0.15 <= taxa <= 2.5 and gap < 4:
                    nome = self._nome(h[-1][3]) or tr("O carro de trás", "The car behind")
                    self.falar(tr(f"{nome} está tirando {falas.dif(taxa)} por volta, está a {falas.gap(gap)}. "
                                  f"Atenção na defesa {falas.ultrapassagem(self.pista)}.",
                                  f"{nome} is closing by {falas.dif(taxa)} a lap, gap {falas.gap(gap)}. "
                                  f"Defend {falas.ultrapassagem(self.pista)}."), 1, "tendencia-tras", 150)

        # janela de parada (estratégia do jogo)
        if self.av["janela_de_parada"] and self.paradas == 0 and self.pit_ideal > 0 and faltam > 3:
            if volta_concluida == self.pit_ideal - 2:
                self.falar(tr(f"Estratégia do jogo: parada ideal na volta {self.pit_ideal}, limite na volta "
                              f"{self.pit_limite}.", f"The game's strategy: ideal stop on lap {self.pit_ideal}, "
                              f"latest on lap {self.pit_limite}."), 1, "janela-aviso", 9999)
            elif volta_concluida == self.pit_ideal - 1:
                self.falar(tr("Janela de parada aberta. Box nesta volta se for seguir a estratégia do jogo.",
                              "Pit window open. Box this lap if you follow the game's strategy."), 1,
                           "janela-box", 9999)

        # combustível
        if self.av["combustivel"] and faltam > 2 and (volta_concluida == 3 or volta_concluida % 6 == 0):
            s = self.comb_sobra_voltas
            if s < -0.2:
                self.falar(tr(f"Combustível curto: falta {falas.voltas(s)} de combustível. Tire o pé um pouco "
                              f"antes das freadas para economizar.",
                              f"Fuel is short by {falas.voltas(s)}. Lift and coast before the braking zones."), 2, "comb", 60)
            elif s > 1.0 and volta_concluida == 3:
                self.falar(tr(f"Combustível sobrando, {falas.voltas(s)} a mais. Pode forçar.",
                              f"Plenty of fuel, {falas.voltas(s)} extra. You can push."), 0, "comb", 60)
            elif volta_concluida == 3:
                self.falar(tr("Combustível ok para o fim da corrida.", "Fuel is fine to the end."), 0, "comb", 60)

        # últimas voltas
        if self.av["ultimas_voltas"] and self.total_voltas:
            if faltam == 5:
                self.falar(tr("Faltam 5 voltas.", "5 laps to go."), 1, "faltam5", 9999)
            elif faltam == 1:
                self.falar(tr("Última volta! Traga o carro para casa.", "Last lap! Bring it home."), 2, "ultima", 9999)

    def _carro_na_posicao(self, pos):
        if pos < 1:
            return None
        for c in self.carros:
            if c.posicao == pos and c.status_resultado in (2, 3):
                return c
        return None

    # ---------------- equipes ----------------
    def equipe_carro(self, c):
        """Equipe do carro: primeiro pelo id que o jogo manda (certo até no modo carreira, quando os
        pilotos trocam de equipe); se o id for desconhecido (equipe própria, genérica), pelo nome do piloto."""
        if c.equipe in ID_EQUIPE:
            return ID_EQUIPE[c.equipe]
        if c.equipe in self.equipe_por_id:
            return self.equipe_por_id[c.equipe]
        eq = equipe_do_nome(c.nome)
        if eq:
            return eq
        parceiro = c.idx ^ 1     # o jogo põe os dois carros da mesma equipe lado a lado
        if 0 <= parceiro < len(self.carros):
            p = self.carros[parceiro]
            if p.equipe in ID_EQUIPE:
                return ID_EQUIPE[p.equipe]
            return equipe_do_nome(p.nome) or ""
        return ""

    def cor_carro(self, c):
        eq = self.equipe_carro(c)
        return EQUIPES[eq][1] if eq in EQUIPES else "#888888"

    # ---------------- 2026: modo straight e overtake ----------------
    def on_telemetria2(self, p):
        dados = getattr(p, "m_carTelemetry2Data", None) or []
        if self.jogador >= len(dados):
            return
        t = dados[self.jogador]
        if not iv(getattr(t, "m_2026Regulations", 0)):
            return
        self.aero_modo = "straight" if iv(t.m_activeAeroMode) == 1 else "curva"
        disp, ativo = bool(t.m_overtakeAvailable), bool(t.m_overtakeActive)
        self.overtake_estado = "ativo" if ativo else ("disponivel" if disp else "")
        self.overtake_dist = iv(t.m_overtakeActivationDistance)
        eu = self.eu
        # aprende no mapa onde o Overtake fica disponível
        if disp and not self._ot_disp_ant and self.mapa is not None and eu.x is not None and not self._pit_status:
            self.mapa.marcar_overtake(eu.x, eu.z)
        if (disp and not self._ot_disp_ant and self.eh_corrida and eu.volta > 1 and not self._pit_status
                and self.safety_car == 0):
            frente, gf = self.gap_frente()
            if frente is not None and gf is not None and gf < 1.2:
                self.falar(tr(f"Overtake disponível! Ataque {self._nome(frente.idx) or 'o carro da frente'}.",
                              f"Overtake available! Attack {self._nome(frente.idx) or 'the car ahead'}."), 1,
                           "overtake", 25)
        self._ot_disp_ant = disp

    def _guardar_dist(self, idx, total):
        h = self.hist_dist.get(idx)
        if h is None:
            h = self.hist_dist[idx] = deque(maxlen=700)
        t = self.tempo_sessao
        if h and (total < h[-1][1] - 50 or t < h[-1][0]):   # flashback / reinício: recomeça o histórico
            h.clear()
        if not h or t - h[-1][0] >= 0.2:
            h.append((t, total))

    def diferenca(self, idx_tras, idx_frente):
        """Segundos entre dois carros: quanto tempo faz que o da frente passou onde o de trás está agora.
        É o mesmo cálculo da cronometragem oficial. Se não der para calcular, usa o número do jogo."""
        hf, ht = self.hist_dist.get(idx_frente), self.hist_dist.get(idx_tras)
        if hf and ht and len(hf) > 5:
            alvo = ht[-1][1]
            if hf[0][1] <= alvo <= hf[-1][1]:
                lista = list(hf)
                for k in range(len(lista) - 1, 0, -1):
                    (t0, d0), (t1, d1) = lista[k - 1], lista[k]
                    if d0 <= alvo <= d1:
                        tp = t0 + (t1 - t0) * ((alvo - d0) / (d1 - d0) if d1 > d0 else 0)
                        gap = ht[-1][0] - tp
                        if 0 <= gap < 120:
                            return gap
                        break
        if 0 <= idx_tras < len(self.carros):
            ms = self.carros[idx_tras].dif_frente_ms
            if ms > 0:
                return ms / 1000
        return None

    def gap_frente(self):
        f = self._carro_na_posicao(self.eu.posicao - 1)
        return (f, self.diferenca(self.jogador, f.idx)) if f is not None else (None, None)

    def gap_tras(self):
        t = self._carro_na_posicao(self.eu.posicao + 1)
        return (t, self.diferenca(t.idx, self.jogador)) if t is not None else (None, None)

    def _foto_posicoes(self):
        self.pos_foto = {c.idx: (c.posicao, c.paradas) for c in self.carros
                         if c.posicao and c.status_resultado in (2, 3)}

    def _regra_posicao(self):
        eu = self.eu
        agora = time.monotonic()
        if self._pit_status and eu.volta > 1:
            if not self.voltando_box:
                self.paradas_antes_box = eu.paradas
            self.voltando_box = True
            self.fim_box = None
            self.pos_pendente = None
            return
        if eu.volta <= 1 or not eu.posicao:
            self.pos_pendente = None
            if eu.volta <= 1:
                self.pos_anunciada = eu.posicao
                self._foto_posicoes()
            return
        if self.voltando_box:
            # espera as posições assentarem depois da sua parada e diz onde voltou
            if self.fim_box is None:
                self.fim_box = agora
            if agora - self.fim_box < 4:
                return
            self.voltando_box = False
            frente, gf = self.gap_frente()
            tras, gt = self.gap_tras()
            self.falar(falas.volta_do_box(eu.posicao, self._nome(frente.idx) if frente else "", gf,
                                          self._nome(tras.idx) if tras else "", gt,
                                          eu.paradas > getattr(self, "paradas_antes_box", eu.paradas) or eu.idade_pneu <= 1),
                       1, "volta-box", 20)
            self.evento(tr(f"Voltou dos boxes em P{eu.posicao}", f"Rejoined from the pits in P{eu.posicao}"))
            self.pos_anunciada = eu.posicao
            self._foto_posicoes()
            return
        if not self.pos_anunciada:
            self.pos_anunciada = eu.posicao
            self._foto_posicoes()
            return
        if eu.posicao == self.pos_anunciada:
            self.pos_pendente = None
            self._foto_posicoes()
            return
        if self.pos_pendente is None or self.pos_pendente[0] != eu.posicao:
            self.pos_pendente = (eu.posicao, agora)
            return
        if agora - self.pos_pendente[1] < 3:
            return
        self._anunciar_posicao(self.pos_anunciada, eu.posicao)
        self.evento(tr("Posição", "Position") + f": P{self.pos_anunciada} -> P{eu.posicao}")
        self.pos_anunciada = eu.posicao
        self.pos_pendente = None
        self._foto_posicoes()

    def _anunciar_posicao(self, antes, agora_pos):
        """Descobre por que a posição mudou e fala como um engenheiro de verdade."""
        eu = self.eu
        t = time.monotonic()
        recentes = [u for u in self.ultrapassagens if t - u[0] < 20]
        faltam = self.total_voltas - eu.volta + 1 if self.total_voltas else None
        passados, box, fora, me_passaram = [], [], [], []
        for c in self.carros:
            if c.idx == self.jogador or c.idx not in self.pos_foto:
                continue
            pos_ant, paradas_ant = self.pos_foto[c.idx]
            if pos_ant < antes and (c.posicao > agora_pos or c.status_resultado not in (2, 3)):
                if c.status_resultado not in (2, 3):
                    fora.append(c)
                elif c.pit_status or c.paradas > paradas_ant:
                    box.append(c)
                else:
                    passados.append(c)
            elif pos_ant > antes and 0 < c.posicao < agora_pos:
                me_passaram.append(c)
        nome = lambda c: self._nome(c.idx)  # noqa: E731
        if agora_pos < antes:   # ganhou
            if passados:
                # se o jogo manda o evento de ultrapassagem, só elogia o que ele confirmou
                confirmados = [c for c in passados if any(u[1] == self.jogador and u[2] == c.idx for u in recentes)]
                na_pista = confirmados if self.viu_ovtk else passados
                if len(na_pista) >= 2:
                    self.falar(falas.varias_ultrapassagens(len(na_pista), agora_pos), 1, "pos", 4)
                    return
                if na_pista:
                    c = na_pista[0]
                    frente, gf = self.gap_frente()
                    tras, gt = self.gap_tras()
                    self.falar(falas.ultrapassei(nome(c), agora_pos, nome(frente) if frente else "", gf, gt, faltam),
                               1, "pos", 4)
                    return
                c = passados[0]
                self.falar(tr(f"{nome(c) or 'O carro da frente'} perdeu tempo. Ganhamos a posição, P{agora_pos}.",
                              f"{nome(c) or 'The car ahead'} lost time. We gained the place, P{agora_pos}."),
                           1, "pos", 4)
                return
            self.falar(falas.ganhou_sem_ultrapassar([nome(c) for c in box], [nome(c) for c in fora], agora_pos),
                       1, "pos", 4)
            return
        # perdeu
        if not me_passaram:
            self.falar(tr(f"Perdemos posição. Agora P{agora_pos}.", f"We lost a place. Now P{agora_pos}."), 1, "pos", 4)
            return
        if len(me_passaram) >= 2:
            self.falar(falas.perdeu_varias(len(me_passaram), agora_pos), 1, "pos", 4)
            return
        c = me_passaram[0]
        houve = any(u[1] == c.idx and u[2] == self.jogador for u in recentes)
        if self.viu_ovtk and not houve:
            motivo = "erro"
        elif eu.idade_pneu - c.idade_pneu >= 6 or (c.pneu in (16, 19, 20) and eu.pneu in (17, 18, 21, 22)
                                                    and eu.idade_pneu - c.idade_pneu >= 2):
            motivo = "pneu"
        else:
            motivo = ""
        self.falar(falas.ultrapassado(nome(c), agora_pos, motivo, self.diferenca(self.jogador, c.idx), faltam,
                                      self.pista),
                   1, "pos", 4)

    def _regra_carro_tras(self):
        lim = self.av["carro_de_tras_perto_segundos"]
        eu = self.eu
        if not lim or eu.volta <= 2 or self._pit_status:
            return
        tras, dif = self.gap_tras()
        if tras is None or not dif or tras.pit_status:
            return
        faltam = self.total_voltas - eu.volta + 1 if self.total_voltas else 99
        if dif < lim and faltam <= 3:
            nome = self._nome(tras.idx)
            self.falar(tr(f"Defenda! {nome + ' está' if nome else 'O carro de trás está'} a {falas.gap(dif)}. "
                          f"Ele vai tentar {falas.ultrapassagem(self.pista)}.",
                          f"Defend! {nome + ' is' if nome else 'The car behind is'} {falas.gap(dif)} back. "
                          f"He will try {falas.ultrapassagem(self.pista)}."), 2, "defenda", 50)
            self.carro_tras_perto = True
        elif dif < lim and not self.carro_tras_perto:
            self.carro_tras_perto = True
            nome = self._nome(tras.idx)
            self.falar(tr(f"{nome or 'O carro de trás'} está chegando, a {falas.gap(dif)}. Ele já pode usar o Overtake.",
                          f"{nome or 'The car behind'} is closing in, {falas.gap(dif)} back. He can use Overtake now."),
                       1, "tras", 45)
        elif dif > lim + 0.3:
            self.carro_tras_perto = False

    def _regra_bandeirada(self):
        st = self.eu.status_resultado
        if st == 3 and self.ult_status_resultado != 3:
            self.posicao_final = self.eu.posicao
            # em fim de semana com sprint, não dá para ter certeza se esta corrida é a sprint
            sprint = None if any(t in (10, 11, 12, 13, 14) for t in self.estrutura) else False
            txt = falas.fim_corrida(self.eu.posicao, self.posicao_largada, sprint,
                                    self.dono_volta_rapida == self.jogador)
            self.falar(tr("Bandeira quadriculada! ", "Chequered flag! ") + txt, 2, "fim", 9999)
            self.evento(tr(f"Terminou em P{self.eu.posicao}", f"Finished P{self.eu.posicao}"))
            licao = self._licao_da_corrida()
            if licao:
                self.falar(licao, 1, "licao", 9999)
        self.ult_status_resultado = st

    def _regra_penalidades(self, ld):
        pen = iv(ld.m_penalties)
        adv = iv(getattr(ld, "m_cornerCuttingWarnings", 0))
        dt = iv(ld.m_numUnservedDriveThroughPens)
        sg = iv(ld.m_numUnservedStopGoPens)
        if pen > self.penalidades_seg:
            self.falar(tr(f"Penalidade de {pen - self.penalidades_seg} segundos. Total: {pen} segundos.",
                          f"{pen - self.penalidades_seg} second penalty. Total: {pen} seconds."), 2, "pen")
            self.evento(tr(f"Penalidade de tempo: total {pen}s", f"Time penalty: total {pen}s"))
        if adv > self.advertencias:
            self.falar(tr(f"Advertência por limite de pista. Você tem {adv}.",
                          f"Track limits warning. You have {adv}."), 1, "adv", 5)
            self.evento(tr(f"Advertência limite de pista ({adv})", f"Track limits warning ({adv})"))
        if dt > self.drive_through:
            self.falar(tr("Drive-through para cumprir.", "Drive-through penalty to serve."), 3, "dt")
            self.evento("Drive-through")
        if sg > self.stop_go:
            self.falar(tr("Stop and go para cumprir.", "Stop and go penalty to serve."), 3, "sg")
            self.evento("Stop and go")
        self.penalidades_seg, self.advertencias, self.drive_through, self.stop_go = pen, adv, dt, sg

    def _regra_corte(self, apos_minha_volta):
        if self.tipo in CORTE_Q1:
            n = self.n_carros_ativos or 22
            corte = n - max(1, (n - 10) // 2)
        elif self.tipo in CORTE_Q2:
            corte = 10
        else:
            if apos_minha_volta and self.eu.melhor_ms:
                self.falar(tr(f"Você está P{self.eu.posicao}.", f"You are P{self.eu.posicao}."), 0, "posq", 5)
            return
        eu = self.eu
        if not eu.melhor_ms or not eu.posicao:
            return
        melhores = sorted((c.melhor_ms, c.idx) for c in self.carros if c.melhor_ms > 0)
        if apos_minha_volta:
            if eu.posicao <= corte:
                prox = melhores[corte][0] if len(melhores) > corte else 0
                txt = tr(f"Você está P{eu.posicao}, fora da zona de corte.",
                         f"You are P{eu.posicao}, out of the drop zone.")
                if prox:
                    m = falas.dif((prox - eu.melhor_ms) / 1000)
                    txt += tr(f" Margem de {m} para o P{corte + 1}.", f" {m} margin to P{corte + 1}.")
                self.falar(txt, 1, "corte", 5)
            else:
                alvo = melhores[corte - 1][0] if len(melhores) >= corte else 0
                txt = tr(f"Você está P{eu.posicao}, na zona de eliminação.",
                         f"You are P{eu.posicao}, in the drop zone.")
                if alvo:
                    m = falas.dif((eu.melhor_ms - alvo) / 1000 + 0.001)
                    txt += tr(f" Precisa de {m} para passar o P{corte}.", f" You need {m} to beat P{corte}.")
                self.falar(txt, 2, "corte", 5)
            self._dentro_corte = eu.posicao <= corte
        else:
            dentro_antes = getattr(self, "_dentro_corte", None)
            if dentro_antes and eu.posicao > corte:
                self._dentro_corte = False
                self.falar(tr(f"Atenção: você caiu para P{eu.posicao}, zona de eliminação.",
                              f"Careful: you dropped to P{eu.posicao}, in the drop zone."), 2, "caiu", 20)
            elif dentro_antes is not None and eu.posicao <= corte:
                self._dentro_corte = True

    def _regra_minutos_finais(self):
        mins = self.av["classificacao_minutos_finais"]
        if not mins or not self.tempo_restante or self.tempo_restante > mins * 60 or self.tempo_restante < 30:
            return
        chave = f"min-finais-{self.tipo}"
        if chave in self.avisos_feitos:
            return
        self.avisos_feitos.add(chave)
        if self.eu.status_piloto == 0:
            self.falar(tr(f"Faltam {mins} minutos. Hora de sair para a última tentativa. A pista está no melhor momento.",
                          f"{mins} minutes to go. Time to head out for the final run. The track is at its best."),
                       2, chave)
        else:
            self.falar(tr(f"Faltam {mins} minutos. Garanta que vai abrir a volta rápida antes da bandeirada.",
                          f"{mins} minutes to go. Make sure you start your flying lap before the flag."), 2, chave)

    def _regra_clima(self, clima_antes):
        molhado_antes, molhado = clima_antes >= 3, self.clima >= 3
        if self.clima != clima_antes:
            self.evento(tr("Clima", "Weather") + f": {CLIMA.get(clima_antes)} -> {CLIMA.get(self.clima)}")
            if molhado and not molhado_antes:
                txt = tr(f"Começou a {CLIMA.get(self.clima)}.", f"It has started to rain: {CLIMA.get(self.clima)}.")
                if self.eu.pneu in PNEUS_SECOS:
                    txt += tr(" Você está de pneu de seco: fique atento, pode ser hora do intermediário.",
                              " You are on slicks: stay alert, it may be time for inters.")
                self.falar(txt, 2, "clima-agora", 20)
            elif molhado_antes and not molhado:
                self.falar(tr("A chuva parou. A pista vai secar aos poucos; observe os tempos de quem está de pneu de seco.",
                              "The rain has stopped. The track will dry slowly; watch the lap times of anyone on slicks."),
                           2, "clima-agora", 20)
            elif molhado and self.clima > clima_antes:
                self.falar(tr(f"A chuva aumentou: {CLIMA.get(self.clima)}.", f"The rain is getting heavier: {CLIMA.get(self.clima)}."),
                           2, "clima-agora", 20)

        # previsão
        if not self.duracao or not self.previsao:
            return
        decorrido = (self.duracao - self.tempo_restante) / 60
        prox = [x for x in self.previsao if x[0] == self.tipo and x[1] > decorrido]
        prox.sort(key=lambda x: x[1])
        for _, offset, clima_prev, chuva_pct in prox:
            if (clima_prev >= 3) != molhado:
                faltam = offset - decorrido
                if faltam > 15:
                    break
                marco = 5 if faltam <= 5 else 15
                chave = f"prev-{self.tipo}-{offset}-{clima_prev >= 3}-{marco}"
                if chave in self.avisos_feitos:
                    break
                self.avisos_feitos.add(chave)
                if clima_prev >= 3:
                    txt = tr(f"Previsão: {CLIMA.get(clima_prev)} em cerca de {max(1, round(faltam))} minutos, "
                             f"{chuva_pct} por cento de chance.",
                             f"Forecast: {CLIMA.get(clima_prev)} in about {max(1, round(faltam))} minutes, "
                             f"{chuva_pct} percent chance.")
                else:
                    txt = tr(f"Previsão: a chuva deve parar em cerca de {max(1, round(faltam))} minutos.",
                             f"Forecast: the rain should stop in about {max(1, round(faltam))} minutes.")
                self.falar(txt, 1, None)
                self.evento(txt)
                break

    def _regra_safety_car(self, sc_antes):
        if self.safety_car == sc_antes:
            return
        if self.safety_car in (1, 2) and sc_antes in (0, 3):
            nome = tr("Safety Car virtual", "Virtual Safety Car") if self.safety_car == 2 else "Safety Car"
            self.evento(tr(f"{nome} na pista", f"{nome} deployed"))
            volta = max(1, self.eu.volta)
            feitas = volta - 1
            faltam = self.total_voltas - feitas if self.total_voltas else 0
            desg = max(self.eu.desgaste)
            cedo = feitas < max(5, int(self.total_voltas * 0.2)) if self.total_voltas else feitas < 5
            r = None
            try:
                r = self.calcular_plano(self.safety_car)
            except Exception:  # noqa: BLE001
                pass
            if faltam and faltam <= 3:
                dica = tr("Faltam poucas voltas: fique na pista.", "Only a few laps left: stay out.")
            elif r and r[0]["paradas"] and r[0]["paradas"][0][0] == 1:
                dica = (tr(f"Box, box! Com o {nome} a parada sai barata: vamos de {falas_pneu(r[0]['paradas'][0][1])}. ",
                           f"Box, box! Under the {nome} the stop is cheap: we go to the {falas_pneu(r[0]['paradas'][0][1])}. ")
                        + (self._texto_plano(*r) if len(r[0]["paradas"]) > 1 else ""))
            elif r:
                dica = tr("Fique na pista. ", "Stay out. ") + self._texto_plano(*r)
            elif self.paradas == 0 and not cedo:
                dica = tr("Bom momento para parar: a parada fica barata. Box, box!",
                          "Good moment to stop: the stop is cheap. Box, box!")
            elif self.paradas >= 1 and desg < 55:
                dica = tr("Você já parou e os pneus estão bons: fique na pista.",
                          "You have already stopped and the tyres are good: stay out.")
            elif self.paradas >= 1:
                dica = tr(f"Pneus com {desg:.0f} por cento. Se precisar parar de novo, esta é a hora; "
                          f"senão, fique na pista.",
                          f"Tyres at {desg:.0f} percent. If you need to stop again, this is the moment; "
                          f"otherwise, stay out.")
            else:
                dica = tr("Ainda é cedo para parar, fique na pista.", "It's still early to stop, stay out.")
            self.falar(f"{nome}! {dica}", 3, "sc", 5)
        elif self.safety_car == 0 and sc_antes in (1, 2):
            self.falar(tr("Pista liberada. Bandeira verde!", "Track is clear. Green flag!"), 2, "sc-fim", 20)
            self.evento(tr("Safety Car recolhido", "Safety Car in"))

    def _regra_ritmo_pneus(self, c):
        if c.pneu not in PNEUS_SECOS and c.pneu not in PNEUS_CHUVA:
            return
        if not c.ultima_ms or c.teve_pit:
            return
        eu_seco = c.pneu in PNEUS_SECOS
        outros = [o.ultima_ms for o in self.carros
                  if o.idx != c.idx and o.ultima_ms and o.ultima_valida and not o.ultima_teve_pit
                  and o.ultima_volta_num >= c.volta - 1
                  and ((o.pneu in PNEUS_CHUVA) if eu_seco else (o.pneu in PNEUS_SECOS))]
        if len(outros) < 2:
            return
        dif = (c.ultima_ms - statistics.median(outros)) / 1000
        if dif > 1.0:
            if eu_seco:
                txt = tr(f"Quem está de intermediário está {falas.dif(dif)} mais rápido por volta. "
                         f"Considere trocar para intermediário.",
                         f"Cars on inters are {falas.dif(dif)} a lap faster. Consider switching to inters.")
            else:
                txt = tr(f"Quem está de pneu de seco está {falas.dif(dif)} mais rápido por volta. "
                         f"Hora de trocar para pneu de seco.",
                         f"Cars on slicks are {falas.dif(dif)} a lap faster. Time to switch to slicks.")
            self.falar(txt, 3, "ritmo-pneus", 120)
            self.evento(txt)

    # ---------------- painel ----------------
    def snapshot(self):
        eu = self.eu
        cat = "corrida" if self.eh_corrida else ("classificacao" if self.eh_classif else "treino")
        ativos = [c for c in self.carros if c.posicao > 0 and (c.ativo or c.status_resultado in (2, 3)
                                                               or c.idx == self.jogador)]
        ativos.sort(key=lambda c: c.posicao)
        p1_melhor = min((c.melhor_ms for c in ativos if c.melhor_ms), default=0)
        carros = []
        ant = None
        for c in ativos:
            if cat == "corrida":
                g = self.diferenca(c.idx, ant.idx) if ant is not None else None
                dif, dif_lider = (int(g * 1000) if g is not None else c.dif_frente_ms), c.dif_lider_ms
                ant = c
            else:
                dif = (c.melhor_ms - p1_melhor) if (c.melhor_ms and p1_melhor) else 0
                dif_lider = dif
            carros.append({
                "i": c.idx, "pos": c.posicao, "nome": c.nome, "cor": self.cor_carro(c),
                "equipe": EQUIPES.get(self.equipe_carro(c), ("", ""))[0],
                "dif": dif, "dif_lider": dif_lider, "pneu": c.pneu, "idade": c.idade_pneu,
                "paradas": c.paradas, "ultima": c.ultima_ms, "melhor": c.melhor_ms, "pit": c.pit_status,
                "status": c.status_piloto, "resultado": c.status_resultado,
                "x": c.x, "z": c.z, "eu": c.idx == self.jogador, "volta": c.volta,
                "desgaste": round(max(c.desgaste), 0) if c.desgaste else 0,
            })
        t = self.telemetria
        eu_d = {"pos": eu.posicao, "volta": eu.volta, "pneu": eu.pneu, "idade": eu.idade_pneu,
                "desgaste": [round(x, 1) for x in eu.desgaste], "comb": round(self.combustivel, 1),
                "comb_sobra": round(self.comb_sobra_voltas, 2), "ers": round(self.ers / 4e6 * 100),
                "ers_modo": self.ers_modo, "dano": self.dano, "tempo_volta": self.tempo_volta_atual,
                "setor": getattr(self, "_setor", 0), "s1": eu.s1, "s2": eu.s2, "invalida": eu.invalida,
                "pit": getattr(self, "_pit_status", 0), "paradas": self.paradas,
                "aero": self.aero_modo, "overtake": self.overtake_estado, "ot_dist": self.overtake_dist,
                "penalidades": self.penalidades_seg, "advertencias": self.advertencias,
                "melhor": self.melhor_ms, "melhores_setores": self.melhor_setores, "drs_ok": self.drs_permitido,
                "rpm_max": self.rpm_max, "delta": self.delta_ms, "rejoin": self.rejoin}
        if t is not None:
            eu_d.update({"vel": iv(t.m_speed), "marcha": iv(t.m_gear), "rpm": iv(t.m_engineRPM),
                         "acel": round(float(t.m_throttle), 2), "freio": round(float(t.m_brake), 2),
                         "drs": iv(t.m_drs), "temp_sup": [iv(x) for x in t.m_tyresSurfaceTemperature],
                         "temp_int": [iv(x) for x in t.m_tyresInnerTemperature],
                         "temp_freio": [iv(x) for x in t.m_brakesTemperature]})
        return {
            "sessao": {"nome": self.nome_sessao, "pista": self.nome_pista, "categoria": cat,
                       "volta": eu.volta, "total": self.total_voltas, "restante": self.tempo_restante,
                       "clima": CLIMA.get(self.clima, ""), "clima_id": self.clima, "temp_pista": self.temp_pista,
                       "temp_ar": self.temp_ar, "sc": self.safety_car, "pausado": self.pausado},
            "mapa_versao": self.mapa.versao if self.mapa else 0,
            "carros": carros, "eu": eu_d, "pecas": self.pecas,
            "voltas": self.voltas[-10:],
            "melhores_sessao": self.melhores_sessao,
        }

    # ---------------- resumo ----------------
    def escrever_resumo(self):
        if not self.info_ok or not self.cfg.get("gravar_telemetria", True) or not self.voltas and not self.eventos:
            return
        self._abrir_pasta()
        L = []
        L.append(tr("RESUMO DA SESSÃO", "SESSION SUMMARY"))
        L.append("=" * 60)
        L.append(tr(f"Pista: {self.nome_pista}   Sessão: {self.nome_sessao}   Início: {self.inicio:%d/%m/%Y %H:%M}",
                    f"Track: {self.nome_pista}   Session: {self.nome_sessao}   Start: {self.inicio:%Y-%m-%d %H:%M}"))
        if self.clima_inicial:
            cl, tp, ta = self.clima_inicial
            L.append(tr(f"Clima no início: {CLIMA.get(cl, cl)}, pista {tp}°C, ar {ta}°C",
                        f"Weather at the start: {CLIMA.get(cl, cl)}, track {tp}°C, air {ta}°C"))
        if self.posicao_largada and self.eh_corrida:
            L.append(tr("Largada", "Grid") + f": P{self.posicao_largada}   Final: P{self.posicao_final or self.posicao}")
        elif self.posicao:
            L.append(tr("Posição final", "Final position") + f": P{self.posicao}")
        L.append("")

        if self.acertos:
            volta, a = self.acertos[-1]
            L.append(tr("ACERTO USADO", "SETUP USED")
                     + (tr(" (último registrado)", " (last recorded)") if len(self.acertos) > 1 else ""))
            D, T = tr("D", "F"), tr("T", "R")
            L.append(tr(f"  Asas: dianteira {a['frontWing']:.0f} | traseira {a['rearWing']:.0f}",
                        f"  Wings: front {a['frontWing']:.0f} | rear {a['rearWing']:.0f}"))
            L.append(tr(f"  Diferencial: ativa {a['onThrottle']:.0f}% | inativa {a['offThrottle']:.0f}%",
                        f"  Differential: on throttle {a['onThrottle']:.0f}% | off throttle {a['offThrottle']:.0f}%"))
            L.append(tr("  Cambagem", "  Camber") + f": {D} {a['frontCamber']:.2f} | {T} {a['rearCamber']:.2f}   "
                     f"Toe: {D} {a['frontToe']:.2f} | {T} {a['rearToe']:.2f}")
            L.append(tr("  Suspensão", "  Suspension") + f": {D} {a['frontSuspension']:.0f} | {T} {a['rearSuspension']:.0f}   "
                     + tr("Barras", "Anti-roll bars") + f": {D} {a['frontAntiRollBar']:.0f} | {T} {a['rearAntiRollBar']:.0f}   "
                     + tr("Altura", "Ride height") + f": {D} {a['frontSuspensionHeight']:.0f} | {T} {a['rearSuspensionHeight']:.0f}")
            L.append(tr(f"  Freios: pressão {a['brakePressure']:.0f}% | balanço {a['brakeBias']:.0f}%",
                        f"  Brakes: pressure {a['brakePressure']:.0f}% | bias {a['brakeBias']:.0f}%"))
            L.append(tr("  Pneus: DE", "  Tyres: FL") + f" {a['frontLeftTyrePressure']:.1f} " + tr("DD", "FR")
                     + f" {a['frontRightTyrePressure']:.1f} " + tr("TE", "RL") + f" {a['rearLeftTyrePressure']:.1f} "
                     + tr("TD", "RR") + f" {a['rearRightTyrePressure']:.1f} psi   "
                     + tr("Combustível", "Fuel") + f": {a['fuelLoad']:.1f} kg")
            L.append("")

        if self.voltas:
            L.append(tr("VOLTAS", "LAPS"))
            L.append(f"  {tr('Nº', 'No'):>3} {tr('Tempo', 'Time'):>9} {'S1':>8} {'S2':>8} {'S3':>8}  "
                     f"{tr('Tipo', 'Type'):<8} {tr('Pneu', 'Tyre'):<13} "
                     f"{tr('Desg%', 'Wear%'):>5} {tr('Comb', 'Fuel'):>5}  " + tr("Obs", "Notes"))
            tipos_en = {"rápida": "push", "saída": "out", "entrada": "in", "normal": "normal",
                        "corrida": "race", "safety car": "safety car"}
            for v in self.voltas:
                obs = []
                if not v["valida"]:
                    obs.append(tr("inválida", "invalid"))
                if v["teve_pit"]:
                    obs.append("pit")
                tipo_txt = tr(v["tipo"], tipos_en.get(v["tipo"], v["tipo"]))
                L.append(f"  {v['volta']:>3} {v['tempo']:>9} {tempo_txt(v['s1_ms']):>8} {tempo_txt(v['s2_ms']):>8} "
                         f"{tempo_txt(v['s3_ms']):>8}  {tipo_txt:<8} {str(v['pneu']):<13} "
                         f"{v['desgaste_max_fim']:>5.0f} {v['combustivel_fim_kg']:>5.1f}  {', '.join(obs)}")
            L.append("")
            validas = [v for v in self.voltas if v["valida"] and not v["teve_pit"] and v["tempo_ms"] > 0
                       and v["tipo"] != "safety car" and v["s1_ms"] > 0 and v["s2_ms"] > 0 and v["s3_ms"] > 0]
            if validas:
                melhor = min(validas, key=lambda v: v["tempo_ms"])
                L.append(tr(f"Melhor volta: {melhor['tempo']} (volta {melhor['volta']})",
                            f"Best lap: {melhor['tempo']} (lap {melhor['volta']})"))
                if all(self.melhor_setores):
                    ideal = sum(self.melhor_setores)
                    ganho = (melhor['tempo_ms'] - ideal) / 1000
                    L.append(tr(f"Volta ideal (soma dos melhores setores): {tempo_txt(ideal)}  "
                                f"-> {ganho:.3f} s a ganhar juntando os melhores setores",
                                f"Ideal lap (sum of best sectors): {tempo_txt(ideal)}  "
                                f"-> {ganho:.3f} s to gain by putting the best sectors together"))
                    for k in range(3):
                        sk = f"s{k + 1}_ms"
                        if melhor[sk] and self.melhor_setores[k]:
                            L.append(tr(f"   Setor {k + 1}: melhor {tempo_txt(self.melhor_setores[k])}, "
                                        f"na melhor volta {tempo_txt(melhor[sk])} ",
                                        f"   Sector {k + 1}: best {tempo_txt(self.melhor_setores[k])}, "
                                        f"on the best lap {tempo_txt(melhor[sk])} ")
                                     + f"(+{(melhor[sk] - self.melhor_setores[k]) / 1000:.3f})")
                if self.eh_corrida and len(validas) >= 3:
                    tempos = [v["tempo_ms"] / 1000 for v in validas if v["volta"] > 1]
                    if len(tempos) >= 2:
                        L.append(tr("Média das voltas limpas (sem volta 1, pit e safety car): ",
                                    "Average of clean laps (no lap 1, pit or safety car): ")
                                 + f"{tempo_txt(statistics.mean(tempos) * 1000)}   "
                                 + tr("Consistência (desvio padrão)", "Consistency (standard deviation)")
                                 + f": {statistics.pstdev(tempos):.3f} s")
            # stints
            stints = []
            idade_ant = None
            for v in self.voltas:
                idade = v.get("idade_pneu")
                novo_jogo = idade is not None and idade_ant is not None and idade < idade_ant
                idade_ant = idade
                if not stints or stints[-1]["pneu"] != v["pneu"] or novo_jogo:
                    stints.append({"pneu": v["pneu"], "voltas": [], "desg": [], "comb": []})
                stints[-1]["voltas"].append(v["volta"])
                if not v["teve_pit"]:
                    stints[-1]["desg"].append(v["desgaste_na_volta"])
                    stints[-1]["comb"].append(v["consumo_volta_kg"])
            L.append("")
            L.append("STINTS")
            for s in stints:
                d = statistics.mean([x for x in s["desg"] if x >= 0]) if s["desg"] else 0
                cm = statistics.mean([x for x in s["comb"] if x >= 0]) if s["comb"] else 0
                L.append(tr(f"  {s['pneu']}: voltas {s['voltas'][0]}-{s['voltas'][-1]}  "
                            f"desgaste médio {d:.2f}%/volta  consumo médio {cm:.2f} kg/volta",
                            f"  {s['pneu']}: laps {s['voltas'][0]}-{s['voltas'][-1]}  "
                            f"average wear {d:.2f}%/lap  average fuel use {cm:.2f} kg/lap"))
            L.append("")

        if self.pecas:
            L.append(tr("UNIDADE DE POTÊNCIA E CÂMBIO (desgaste no fim da sessão)",
                        "POWER UNIT AND GEARBOX (wear at the end of the session)"))
            for nome, v in sorted(self.pecas.items(), key=lambda x: -x[1]):
                aviso = tr("  <- trocar", "  <- replace") if v >= 70 else (tr("  <- atenção", "  <- watch") if v >= 50 else "")
                L.append(f"  {nome:<16} {v:>3}%{aviso}")
            L.append("")

        if self.eventos:
            L.append(tr("EVENTOS", "EVENTS"))
            for hora, volta, txt in self.eventos:
                L.append(f"  {hora}  " + tr("volta", "lap") + f" {volta:>2}  {txt}")

        try:
            with open(os.path.join(self.pasta, "resumo.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(L) + "\n")
            with open(os.path.join(self.pasta, "sessao.json"), "w", encoding="utf-8") as f:
                json.dump({"pista": self.nome_pista, "pista_id": self.pista, "sessao": self.nome_sessao,
                           "sessao_tipo": self.tipo, "inicio": self.inicio.isoformat(),
                           "formato_udp": self.formato, "total_voltas": self.total_voltas,
                           "clima_inicial": self.clima_inicial, "posicao_largada": self.posicao_largada,
                           "posicao_final": self.posicao_final or self.posicao, "melhores_setores_ms": self.melhor_setores,
                           "melhor_ms": self.melhor_ms, "voltas_feitas": len(self.voltas),
                           "acertos": [{"volta": v, "acerto": a} for v, a in self.acertos],
                           "eventos": self.eventos}, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"[GRAVAÇÃO] Erro ao salvar o resumo: {e}")


# --------------------------------------------------------------------------------------
# Programa principal
# --------------------------------------------------------------------------------------

PARSERS = {0: PacketMotionData, 1: PacketSessionData, 2: PacketLapData, 3: PacketEventData, 4: PacketParticipantsData,
           5: PacketCarSetupData, 6: PacketCarTelemetryData, 7: PacketCarStatusData, 10: PacketCarDamageData}
if PacketCarTelemetry2Data is not None:
    PARSERS[16] = PacketCarTelemetry2Data


class Engenheiro:
    def __init__(self, cfg, radio):
        self.cfg = cfg
        self.radio = radio
        self.sessao = None
        self.destinos = []
        for d in cfg.get("encaminhar_para") or []:
            try:
                host, porta = d.rsplit(":", 1)
                self.destinos.append((host, int(porta)))
            except ValueError:
                print(f"[AVISO] Destino de encaminhamento inválido: {d}")
        self.sock_envio = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) if self.destinos else None
        self.recebendo = False
        self.formato_avisado = False
        self.erros = 0

    def processar(self, dados):
        if self.sock_envio:
            for dest in self.destinos:
                try:
                    self.sock_envio.sendto(dados, dest)
                except OSError:
                    pass
        if len(dados) < PacketHeader.PACKET_LEN:
            return
        try:
            cab = PacketHeader(dados[:PacketHeader.PACKET_LEN])
        except Exception:  # noqa: BLE001
            return
        if not self.recebendo:
            self.recebendo = True
            print(f"[OK] Recebendo dados do jogo (formato UDP {cab.m_packetFormat}).", flush=True)
            self.radio.falar(tr("Rádio conectado. Estou com você.", "Radio check. I'm with you."), 1, "conectado", 60)
        if cab.m_packetFormat < 2024 and not self.formato_avisado:
            self.formato_avisado = True
            print("[AVISO] Formato UDP antigo. No jogo, use 'Formato UDP' 2025 ou 2026.")
        pid = iv(cab.m_packetId)
        classe = PARSERS.get(pid)
        if classe is None:
            return
        uid = cab.m_sessionUID
        if not uid:
            return
        if uid == self.demo_uid and self._demo_parar is not None and self._demo_parar.is_set():
            return                       # pacotes atrasados de uma demonstração que já foi parada
        try:
            pac = classe(cab, dados[PacketHeader.PACKET_LEN:])
        except Exception as e:  # noqa: BLE001
            self.erros += 1
            if self.erros <= 3:
                print(f"[AVISO] Não consegui ler um pacote tipo {pid}: {e}")
            return

        if self.sessao is None or self.sessao.uid != uid:
            if self.demo_uid and uid != self.demo_uid and self.demo_ativa():
                self.parar_demo()                 # o jogo de verdade chegou: a demonstração para
            if self.sessao is not None:
                self.sessao.fechar()
            if uid == self.demo_uid:
                # demonstração: nada é gravado (sessões, histórico de acertos e de pneus ficam como estão)
                self.sessao = Sessao(uid, dict(self.cfg, gravar_telemetria=False, _demo=True), self.radio)
            else:
                self.sessao = Sessao(uid, self.cfg, self.radio)
        s = self.sessao
        s.formato = cab.m_packetFormat
        jog = iv(cab.m_playerCarIndex)
        if 0 <= jog < len(s.carros):
            s.jogador = jog
        try:
            s.ultimo_pacote = time.monotonic()
            if pid == 0:
                s.on_movimento(pac)
            elif pid == 1:
                s.on_sessao(pac)
            elif pid == 2:
                s.tempo_sessao = float(cab.m_sessionTime)
                s.on_voltas(pac)
            elif pid == 3:
                s.on_evento(pac)
            elif pid == 4:
                s.on_participantes(pac)
            elif pid == 5:
                s.on_acerto(pac)
            elif pid == 6:
                s.on_telemetria(pac, float(cab.m_sessionTime))
            elif pid == 7:
                s.on_status(pac)
            elif pid == 10:
                s.on_dano(pac)
            elif pid == 16:
                s.on_telemetria2(pac)
            elif pid == 12:
                s.on_conjuntos(pac)
        except Exception as e:  # noqa: BLE001
            self.erros += 1
            if self.erros <= 10:
                import traceback
                print(f"[ERRO] Pacote tipo {pid}: {e}")
                traceback.print_exc()

    def fechar(self):
        if self.sessao:
            self.sessao.fechar()

    # ---------------- demonstração (corrida simulada, sem o jogo) ----------------
    demo_uid = 0
    _demo_thread = None
    _demo_parar = None

    def demo_ativa(self):
        return self._demo_thread is not None and self._demo_thread.is_alive()

    def iniciar_demo(self, cenario="corrida"):
        if self.demo_ativa():
            return {"ok": True}
        s = self.sessao
        if s is not None and s.uid != self.demo_uid and time.monotonic() - s.ultimo_pacote < 5:
            return {"ok": False, "erro": tr("O jogo está conectado: a demonstração só roda sem o jogo.",
                                            "The game is connected: the demo only runs without the game.")}
        import simulador
        self._demo_parar = threading.Event()
        self.demo_uid = simulador.preparar_demo(cenario, int(self.cfg.get("porta", 20777)),
                                                self.cfg.get("nome_piloto") or tr("Você", "You"), self._demo_parar)
        self._demo_thread = threading.Thread(target=simulador.rodar_demo, daemon=True)
        self._demo_thread.start()
        print(f"[DEMO] Demonstração iniciada ({cenario}).", flush=True)
        return {"ok": True}

    def parar_demo(self):
        if self._demo_parar is not None:
            self._demo_parar.set()
        if self._demo_thread is not None:
            self._demo_thread.join(2)
        if self.sessao is not None and self.sessao.uid == self.demo_uid:
            self.sessao = None
        self.radio.historico.clear()
        print("[DEMO] Demonstração encerrada.", flush=True)
        return {"ok": True}

    def estado(self):
        """Estado atual para o painel (chamado pela thread do servidor web)."""
        s = self.sessao
        base = {"conectado": False, "radio": list(self.radio.historico), "idioma": idioma.IDIOMA,
                "atualizacao": ATUALIZACAO or None,
                "demo": self.demo_ativa() or bool(s is not None and self.demo_uid and s.uid == self.demo_uid)}
        if s is None or not s.info_ok:
            return base
        for _ in range(3):
            try:
                d = s.snapshot()
                break
            except (RuntimeError, IndexError, AttributeError, ValueError):
                time.sleep(0.01)
        else:
            return base
        d.update(base)
        d["conectado"] = time.monotonic() - s.ultimo_pacote < 3
        return d

    def perguntar(self, tipo):
        if tipo == "ouvir":
            if getattr(self, "microfone", None) is not None:
                self.microfone.ativar_escuta()
            else:
                self.radio.falar(tr("O microfone está desligado nas configurações.", "The microphone is turned off in the settings."),
                                 1, "mic-off", 5)
            return
        if tipo == "silencio":
            self.radio.falar(tr("Entendido. Só falo o que for importante.", "Copy. I'll only call the important stuff."), 2, None)
            self.radio.silencioso = True
            return
        if tipo == "falar":
            self.radio.silencioso = False
            self.radio.falar(tr("Ok, voltando aos avisos normais.", "Ok, back to normal radio."), 2, None)
            return
        if tipo == "nao_entendi":
            self.radio.falar(tr("Não entendi. Pode repetir?", "Didn't get that. Say again?"), 2, None)
            return
        if tipo == "teste_radio":                 # funciona mesmo sem o jogo aberto
            self.radio.teste_de_radio()
            return
        if self.sessao is not None and self.sessao.info_ok:
            self.sessao.perguntar(tipo)
        elif tipo == "repetir":
            self.radio.repetir_ultima()
        else:
            self.radio.falar(tr("Ainda não estou recebendo dados do jogo.", "I'm not receiving game data yet."),
                             1, "sem-dados", 5)

    # ---------------- telas de configurações e histórico ----------------
    CONFIG_EDITAVEL = {
        "idioma": str, "nome_piloto": str, "rivais": str, "microfone_som_escuta": bool, "distancia_corrida_pct": int, "voz_ativada": bool, "voz_neural": str,
        "voz_neural_en": str, "voz_velocidade_neural": str, "voz_efeito_radio": bool, "voz_no_notebook": bool, "microfone": bool,
        "microfone_palavra_ativacao": str, "microfone_frases": str, "porta": int, "porta_painel": int,
        "abrir_painel_automaticamente": bool, "painel_no_celular": bool, "verificar_atualizacoes": bool,
    }
    PRECISA_REINICIAR = {"painel_no_celular", "idioma", "voz_ativada", "microfone", "microfone_palavra_ativacao", "microfone_frases", "porta",
                         "porta_painel"}

    def config_tela(self):
        import voz
        import versao
        sobre = {"nome": versao.NOME, "versao": versao.VERSAO, "subtitulo": list(versao.SUBTITULO),
                 "autor": versao.AUTOR, "github": versao.LINK_GITHUB, "doacao": versao.LINK_DOACAO,
                 "aviso": list(versao.AVISO), "atualizacao": ATUALIZACAO or None, "terceiros": [[n, lic, list(uso)] for n, lic, uso in versao.TERCEIROS]}
        return {"cfg": self.cfg, "vozes": voz.VOZES_SUGERIDAS, "vozes_en": voz.VOZES_EN, "ip": ip_local(),
                "sobre": sobre}

    def salvar_config(self, novo):
        mudou_reiniciar = []
        for k, tipo in self.CONFIG_EDITAVEL.items():
            if k in novo:
                try:
                    v = tipo(novo[k]) if tipo is not bool else bool(novo[k])
                except (TypeError, ValueError):
                    continue
                if self.cfg.get(k) != v:
                    if k in self.PRECISA_REINICIAR:
                        mudou_reiniciar.append(k)
                    self.cfg[k] = v
        avisos = novo.get("avisos") or {}
        for k, v in avisos.items():
            if k not in self.cfg["avisos"]:
                continue
            atual = self.cfg["avisos"][k]
            try:
                if isinstance(atual, bool):
                    v = bool(v)
                elif isinstance(atual, list):
                    v = sorted(int(x) for x in (v if isinstance(v, list) else str(v).replace(";", ",").split(","))
                               if str(x).strip())
                elif isinstance(atual, float):
                    v = float(v)
                elif isinstance(atual, int):
                    v = int(float(v))
            except (TypeError, ValueError):
                continue
            self.cfg["avisos"][k] = v
        # aplica na hora o que dá
        idioma.definir(self.cfg.get("idioma", "pt"))
        r = self.radio
        r.nome_piloto = (self.cfg.get("nome_piloto") or "").strip()
        if getattr(self, "microfone", None) is not None:
            self.microfone.som_escuta = bool(self.cfg.get("microfone_som_escuta", True))
        r.no_notebook = bool(self.cfg.get("voz_no_notebook", True))
        if getattr(r, "neural", None) is not None:
            import voz
            lang = "en" if idioma.en() else "pt"
            r.neural.voz = voz.voz_do_idioma(self.cfg.get("voz_neural_en" if lang == "en" else "voz_neural"), lang)
            r.neural.velocidade = self.cfg.get("voz_velocidade_neural", r.neural.velocidade)
            r.neural.efeito = bool(self.cfg.get("voz_efeito_radio", True))
        try:
            if novo.get("_concluir"):
                self.cfg.pop("_novo", None)
            with open(os.path.join(AQUI, "config.json"), "w", encoding="utf-8") as f:
                json.dump({k: v for k, v in self.cfg.items() if not k.startswith("_")}, f, ensure_ascii=False, indent=4)
        except OSError as e:
            return {"ok": False, "erro": str(e)}
        return {"ok": True, "reiniciar": mudou_reiniciar}

    def _pasta_sessoes(self):
        base = self.cfg.get("pasta_sessoes", "sessoes")
        return base if os.path.isabs(base) else os.path.join(AQUI, base)

    def sessoes_lista(self):
        base = self._pasta_sessoes()
        itens = []
        try:
            nomes = sorted((n for n in os.listdir(base) if os.path.isdir(os.path.join(base, n))), reverse=True)
        except OSError:
            return []
        for n in nomes[:300]:
            pasta = os.path.join(base, n)
            info = {"pasta": n, "arquivos": [a for a in ("resumo.txt", "analise.txt", "relatorio.html", "radio.csv")
                                              if os.path.exists(os.path.join(pasta, a))]}
            try:
                with open(os.path.join(pasta, "sessao.json"), encoding="utf-8") as f:
                    sj = json.load(f)
                ac = (sj.get("acertos") or [{}])[-1].get("acerto") or {}
                info.update({"pista": sj.get("pista"), "sessao": sj.get("sessao"), "inicio": sj.get("inicio"),
                             "posicao": sj.get("posicao_final"), "largada": sj.get("posicao_largada"),
                             "melhor": tempo_txt(sj["melhor_ms"]) if sj.get("melhor_ms") else "",
                             "acerto": {k: ac.get(k) for k in ("frontWing", "rearWing", "onThrottle", "offThrottle",
                                                                "frontAntiRollBar", "rearAntiRollBar")} if ac else {}})
            except (OSError, ValueError, KeyError):
                pass
            itens.append(info)
        return itens

    def arquivo_sessao(self, pasta, arquivo):
        if arquivo not in ("resumo.txt", "analise.txt", "relatorio.html", "radio.csv", "eventos.csv", "voltas.csv"):
            return None
        if "/" in pasta or "\\" in pasta or ".." in pasta:
            return None
        caminho = os.path.join(self._pasta_sessoes(), pasta, arquivo)
        try:
            with open(caminho, "rb") as f:
                return f.read()
        except OSError:
            return None

    def perguntar_texto(self, texto):
        """Pergunta em frase livre (microfone ou caixa de texto do painel)."""
        texto = (texto or "").strip()
        if not texto:
            return ""
        print(f"[PERGUNTA] {texto}", flush=True)
        import microfone
        cmd = microfone.interpretar(texto)
        curta = len(microfone.sem_acento(texto).replace("engenheiro", "").replace("engineer", "").split()) <= 3
        if (cmd in ("silencio", "falar", "repetir") and curta) or cmd == "teste_radio":
            self.perguntar(cmd)
            return cmd
        if self.sessao is None or not self.sessao.info_ok:
            self.radio.falar(tr("Ainda não estou recebendo dados do jogo.", "I'm not receiving game data yet."),
                             1, "sem-dados", 5)
            return ""
        resp = self.sessao.responder_livre(texto)
        if not resp:
            resp = tr("Não entendi essa. Pode perguntar, por exemplo: quanto falta pro carro da frente, "
                      "o pneu aguenta até o fim, ou quando eu paro.",
                      "Didn't get that one. You can ask, for example: what's the gap to the car ahead, "
                      "will the tyres make it to the end, or when do I pit.")
        self.sessao.falar(resp, 2, None)
        return resp

    def mapa(self):
        s = self.sessao
        if s is None or s.mapa is None:
            return {"versao": 0, "completo": False, "pontos": []}
        return s.mapa.dados()


def _instalar_encerramento(eng):
    """Salva a sessão também quando a janela é fechada no X (Windows) ou o processo é encerrado."""
    import signal

    def salvar(*_):
        try:
            print("\nSalvando a sessão...", flush=True)
            eng.fechar()
        except Exception:  # noqa: BLE001
            pass

    def sair(*_):
        salvar()
        os._exit(0)

    try:
        signal.signal(signal.SIGTERM, sair)
    except (ValueError, OSError):
        pass
    if os.name == "nt":
        try:
            import ctypes
            tipo = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

            def ao_fechar(evento):
                if evento in (2, 5, 6):   # fechar janela, logoff, desligar
                    salvar()
                    return 1
                return 0
            eng._ao_fechar = tipo(ao_fechar)   # manter referência viva
            ctypes.windll.kernel32.SetConsoleCtrlHandler(eng._ao_fechar, True)
        except Exception:  # noqa: BLE001
            pass


# usado pela versão em janela (app.py): para encerrar o laço e saber o endereço do painel
PARAR = threading.Event()
ESTADO_APP = {"erro": None, "url": None, "eng": None, "pronto": threading.Event()}


def main(args=None):
    args = sys.argv[1:] if args is None else args
    janela = "--janela" in args
    cfg = carregar_config()

    print("=" * 64)
    import versao
    print(f"  {versao.NOME.upper()} {versao.VERSAO} - {tr(*versao.SUBTITULO)}")
    print("=" * 64)
    if "--ouvir-vozes" in args:
        import voz
        voz.ouvir_vozes(cfg.get("nome_piloto", ""), cfg.get("voz_velocidade_neural", "+8%"))
        return

    radio = Radio(cfg, cfg["voz_ativada"] and "--sem-voz" not in args)

    if "--testar-voz" in args:
        radio.falar(tr("Teste de rádio. Box, box! Pneus com 60 por cento de desgaste. Última volta, traga o carro para casa.",
                       "Radio check. Box, box! Tyres at 60 percent wear. Last lap, bring it home."))
        radio.esperar_fila()
        return

    porta = int(cfg.get("porta", 20777))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("0.0.0.0", porta))
    except OSError:
        msg = tr(f"A porta {porta} já está em uso por outro programa (provavelmente o SimHub ou outro "
                 f"engenheiro aberto). Feche o outro programa, ou mude a porta do SimHub para 20778 (veja o LEIA-ME.txt).",
                 f"Port {porta} is already in use by another program (probably SimHub or another copy of the "
                 f"engineer). Close the other program, or change SimHub to port 20778 (see README.txt).")
        print("\n[ERRO] " + msg)
        ESTADO_APP["erro"] = msg
        ESTADO_APP["pronto"].set()
        if not janela:
            input("\nPressione Enter para sair...")
        return
    sock.settimeout(1.0)

    print("\nNo PS5 (F1 25 > Configurações > Telemetria), use:")
    print(f"   Endereço IP UDP: {ip_local()}")
    print(f"   Porta UDP:       {porta}")
    if cfg.get("encaminhar_para"):
        print(f"\nRepassando os dados para: {', '.join(cfg['encaminhar_para'])} (SimHub)")
    print("\nAguardando dados do jogo... (entre na pista)  |  Para encerrar: Ctrl+C\n", flush=True)

    eng = Engenheiro(cfg, radio)
    _instalar_encerramento(eng)
    if cfg.get("verificar_atualizacoes", True) and "--sem-atualizacao" not in args:
        threading.Thread(target=verificar_atualizacao, daemon=True).start()
    if cfg.get("microfone", True) and "--sem-microfone" not in args:
        import microfone
        eng.microfone = microfone.Microfone(cfg, eng.perguntar, radio, ao_texto=eng.perguntar_texto)
        eng.microfone.iniciar()
    if cfg.get("painel", True):
        import painel
        url = painel.iniciar(eng, int(cfg.get("porta_painel", 8080)), bool(cfg.get("painel_no_celular", True)))
        ESTADO_APP["url"] = url
        if url and janela:
            print(f"Painel ao vivo: {url}   (no celular, na mesma rede: http://{ip_local()}:{cfg.get('porta_painel', 8080)})")
        elif url:
            print(f"Painel ao vivo: {url}   (no celular, na mesma rede: http://{ip_local()}:{cfg.get('porta_painel', 8080)})")
            if cfg.get("abrir_painel_automaticamente", True) and "--sem-navegador" not in args:
                import webbrowser
                webbrowser.open(url)
    ESTADO_APP["eng"] = eng
    ESTADO_APP["pronto"].set()
    try:
        while not PARAR.is_set():
            try:
                dados, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except ConnectionResetError:
                continue
            eng.processar(dados)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            import signal
            signal.signal(signal.SIGINT, signal.SIG_IGN)
        except (ImportError, ValueError):
            pass
        print("\nEncerrando e salvando a sessão...", flush=True)
        eng.fechar()
        if eng.sessao and eng.sessao.pasta:
            print(f"Arquivos salvos em: {eng.sessao.pasta}")


if __name__ == "__main__":
    main()
