# -*- coding: utf-8 -*-
"""
Vozes do rádio do engenheiro.

- "neural": vozes neurais da Microsoft (as mesmas da leitura em voz alta do Edge), bem mais naturais.
            Precisa de internet. As frases fixas ficam guardadas na pasta cache_voz.
- "windows": voz do próprio Windows (funciona sem internet, mais robótica). Usada como reserva.

Opcionalmente aplica um efeito de "rádio de equipe" (som de rádio com chiado e clique).
"""

import array
import asyncio
import base64
import hashlib
import io
import math
import os
import re
import random
import subprocess
import sys
import wave

AQUI = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
ARQUIVO_VOZ_WINDOWS = os.path.join(AQUI, "voz.ps1")
PASTA_CACHE = os.path.join(AQUI, "cache_voz")
TAXA = 24000

VOZ_PADRAO = {"pt": "pt-BR-AntonioNeural", "en": "en-GB-RyanNeural"}


def voz_do_idioma(escolhida, lang):
    """A voz configurada serve para o idioma? Senão, usa a voz padrão do idioma."""
    v = str(escolhida or "")
    if lang == "en":
        return v if v.startswith("en-") else VOZ_PADRAO["en"]
    return v if v.startswith("pt-") or "Multilingual" in v else VOZ_PADRAO["pt"]


VOZES_SUGERIDAS = [
    ("pt-BR-AntonioNeural", "Antônio - brasileiro, masculino"),
    ("en-US-AndrewMultilingualNeural", "Andrew - fala português com sotaque americano, masculino"),
    ("en-US-BrianMultilingualNeural", "Brian - fala português com sotaque americano, masculino"),
    ("pt-BR-FranciscaNeural", "Francisca - brasileira, feminina"),
    ("pt-BR-ThalitaMultilingualNeural", "Thalita - brasileira, feminina"),
]


# --------------------------------------------------------------------------------------
# Dependências (instaladas sozinhas na primeira vez)
# --------------------------------------------------------------------------------------

def garantir_dependencias():
    """Tenta importar edge_tts e soundfile; se faltar, instala com o pip. Retorna True se ok."""
    if getattr(sys, "frozen", False):        # no executável as bibliotecas já vêm junto
        try:
            import edge_tts  # noqa: F401
            import soundfile  # noqa: F401
            return True
        except ImportError:
            return False
    try:
        import edge_tts  # noqa: F401
        import soundfile  # noqa: F401
        return True
    except ImportError:
        pass
    print("[VOZ] Instalando os componentes da voz neural (só na primeira vez, leva uns segundos)...", flush=True)
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                        "edge-tts>=7.0", "soundfile>=0.13"], check=True, timeout=300)
    except Exception as e:  # noqa: BLE001
        print(f"[VOZ] Não consegui instalar ({e}). Vou usar a voz do Windows.")
        return False
    try:
        import importlib
        importlib.invalidate_caches()
        import edge_tts  # noqa: F401,F811
        import soundfile  # noqa: F401,F811
        return True
    except ImportError:
        print("[VOZ] A instalação não funcionou. Vou usar a voz do Windows.")
        return False


# --------------------------------------------------------------------------------------
# Efeito de rádio
# --------------------------------------------------------------------------------------

def _biquad(x, tipo, freq, q=0.707):
    w0 = 2 * math.pi * freq / TAXA
    cw, sw = math.cos(w0), math.sin(w0)
    alfa = sw / (2 * q)
    if tipo == "pb":   # passa-baixa
        b0, b1, b2 = (1 - cw) / 2, 1 - cw, (1 - cw) / 2
    else:              # passa-alta
        b0, b1, b2 = (1 + cw) / 2, -(1 + cw), (1 + cw) / 2
    a0, a1, a2 = 1 + alfa, -2 * cw, 1 - alfa
    b0, b1, b2, a1, a2 = b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0
    y = [0.0] * len(x)
    x1 = x2 = y1 = y2 = 0.0
    for i, xi in enumerate(x):
        yi = b0 * xi + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, xi, y1, yi
        y[i] = yi
    return y


def _banda(x):
    for _ in range(2):
        x = _biquad(x, "pa", 420)
        x = _biquad(x, "pb", 3300)
    return x


_CHIADO = []


def _chiado(n):
    """Chiado de fundo já filtrado (gerado uma vez e reaproveitado)."""
    if len(_CHIADO) < n:
        rnd = random.Random(42)
        _CHIADO[:] = _banda([rnd.uniform(-0.05, 0.05) for _ in range(max(n, 12 * TAXA))])
    return _CHIADO[:n]


def efeito_radio(amostras):
    """Recebe PCM 16 bits mono (24 kHz) e devolve PCM com som de rádio de equipe."""
    rnd = random.Random(len(amostras))
    x = [s / 32768.0 for s in amostras]
    x = _banda(x)
    pico = max((abs(v) for v in x), default=0) or 1.0
    ganho = 2.6 / pico
    x = [math.tanh(v * ganho) / math.tanh(2.6) for v in x]   # leve saturação, como rádio

    def ruido(n, amp):
        return [rnd.uniform(-amp, amp) for _ in range(n)]

    clique_ini = _banda(ruido(int(0.07 * TAXA), 0.9))
    clique_ini = [v * (1 - i / len(clique_ini)) ** 2 for i, v in enumerate(clique_ini)]
    pausa = [0.0] * int(0.06 * TAXA)
    chiado = _chiado(len(x))
    x = [v * 0.82 + c for v, c in zip(x, chiado)]
    clique_fim = _banda(ruido(int(0.12 * TAXA), 0.7))
    clique_fim = [v * (1 - i / len(clique_fim)) for i, v in enumerate(clique_fim)]
    final = clique_ini + pausa + x + [0.0] * int(0.04 * TAXA) + clique_fim
    pico = max((abs(v) for v in final), default=0) or 1.0
    k = 0.9 / pico * 32767
    return array.array("h", (int(max(-32767, min(32767, v * k))) for v in final))


def para_wav(amostras):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes(amostras.tobytes())
    return buf.getvalue()


def tocar_wav(dados):
    """Toca um WAV (bytes) e espera terminar."""
    try:
        import winsound
    except ImportError:
        return  # fora do Windows não toca (só para testes)
    winsound.PlaySound(dados, winsound.SND_MEMORY)


_SOM_ESCUTA = []


def som_escuta():
    """O 'bip' do rádio de equipe (dois toques curtos, baixinho): o engenheiro ouviu você."""
    if not _SOM_ESCUTA:
        x = []
        for freq, dur, pausa in ((1320, 0.055, 0.022), (1760, 0.075, 0.0)):
            n = int(dur * TAXA)
            borda = int(0.006 * TAXA)
            for i in range(n):
                env = min(1.0, i / borda, (n - i) / borda)
                x.append(0.5 * env * math.sin(2 * math.pi * freq * i / TAXA))
            x += [0.0] * int(pausa * TAXA)
        rnd = random.Random(7)
        clique = [rnd.uniform(-0.25, 0.25) * (1 - i / (0.012 * TAXA)) for i in range(int(0.012 * TAXA))]
        x = _banda(clique + [0.0] * int(0.01 * TAXA) + x + [0.0] * int(0.02 * TAXA))
        pico = max((abs(v) for v in x), default=0) or 1.0
        k = 0.22 / pico * 32767          # volume baixo: é só um aviso
        _SOM_ESCUTA.append(para_wav(array.array("h", (int(v * k) for v in x))))
    return _SOM_ESCUTA[0]


def tocar_som_escuta():
    import threading
    threading.Thread(target=lambda: tocar_wav(som_escuta()), daemon=True).start()


def mp3_para_pcm(mp3):
    """Decodifica o MP3 do serviço de voz para PCM 16 bits mono a 24 kHz."""
    import numpy as np
    import soundfile as sf
    dados, taxa = sf.read(io.BytesIO(mp3), dtype="float32", always_2d=True)
    mono = dados.mean(axis=1)
    if taxa != TAXA and len(mono):
        n = int(len(mono) * TAXA / taxa)
        mono = np.interp(np.linspace(0, len(mono) - 1, n), np.arange(len(mono)), mono)
    return array.array("h", (np.clip(mono, -1, 1) * 32767).astype("int16").tobytes())


# --------------------------------------------------------------------------------------
# Motores de voz
# --------------------------------------------------------------------------------------

class VozWindows:
    def __init__(self, velocidade=1, volume=100, idioma="pt"):
        self.proc = None
        self.nome = None
        if os.name != "nt" or not os.path.exists(ARQUIVO_VOZ_WINDOWS):
            return
        try:
            self.proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ARQUIVO_VOZ_WINDOWS,
                 "-Velocidade", str(int(velocidade)), "-Volume", str(int(volume)), "-Idioma", idioma],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="ascii", errors="ignore",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            primeira = self.proc.stdout.readline().strip()
            if not primeira.startswith("VOZ:"):
                raise RuntimeError("resposta inesperada do PowerShell")
            self.nome = primeira[4:]
        except Exception as e:  # noqa: BLE001
            print(f"[VOZ] Não consegui iniciar a voz do Windows ({e}).")
            self.proc = None

    @property
    def ok(self):
        return self.proc is not None and self.proc.poll() is None

    def falar(self, texto):
        if not self.ok:
            return False
        try:
            self.proc.stdin.write(base64.b64encode(pronuncia(texto).encode("utf-8")).decode("ascii") + "\n")
            self.proc.stdin.flush()
            self.proc.stdout.readline()
            return True
        except Exception:  # noqa: BLE001
            self.proc = None
            return False


# Como a voz deve pronunciar os nomes (só muda o áudio; o painel continua com o nome certo).
PRONUNCIA = {
    "Leclerc": "Leclér", "Verstappen": "Vérstapen", "Russell": "Rássel", "Hamilton": "Rêmilton",
    "Norris": "Nórris", "Piastri": "Piástri", "Sainz": "Sáinz", "Stroll": "Estról", "Gasly": "Gaslí",
    "Ocon": "Ocón", "Hulkenberg": "Rúlquenberg", "Hülkenberg": "Rúlquenberg", "Lawson": "Lóson",
    "Hadjar": "Adjár", "Bearman": "Bírman", "Albon": "Álbon", "Lindblad": "Lindblád", "Bottas": "Bótas",
    "Perez": "Pérez", "Tsunoda": "Tsunôda", "Doohan": "Dúan", "Magnussen": "Mágnussen",
    "Ricciardo": "Ritchárdo", "Overtake": "Ôverteique", "Straight": "Istrêit", "Speed trap": "Spíd trép", "Zhou": "Djôu", "Antonelli": "Antonéli", "Bortoleto": "Bortolêto",
}
_RE_PRONUNCIA = re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(PRONUNCIA, key=len, reverse=True)) + r")\b",
                           re.IGNORECASE)
_PRONUNCIA_MIN = {k.lower(): v for k, v in PRONUNCIA.items()}


def pronuncia(texto):
    import idioma
    if idioma.en():      # a voz em inglês já pronuncia os nomes direito
        return texto
    return _RE_PRONUNCIA.sub(lambda m: _PRONUNCIA_MIN.get(m.group(0).lower(), m.group(0)), texto)


class VozNeural:
    def __init__(self, voz="pt-BR-AntonioNeural", velocidade="+8%", efeito=True):
        self.voz = voz
        self.velocidade = velocidade
        self.efeito = efeito
        self.ok = garantir_dependencias()

    async def _baixar(self, texto):
        import edge_tts
        com = edge_tts.Communicate(texto, self.voz, rate=self.velocidade, connect_timeout=6, receive_timeout=15)
        audio = bytearray()
        async for parte in com.stream():
            if parte.get("type") == "audio":
                audio += parte["data"]
        return bytes(audio)

    def gerar_wav(self, texto):
        """Devolve o WAV pronto (com efeito, se ligado). Usa o cache para frases sem números."""
        cacheavel = not any(ch.isdigit() for ch in texto)
        chave = hashlib.sha1(f"{self.voz}|{self.velocidade}|{self.efeito}|{texto}".encode("utf-8")).hexdigest()[:20]
        caminho = os.path.join(PASTA_CACHE, f"{chave}.wav")
        if cacheavel and os.path.exists(caminho):
            with open(caminho, "rb") as f:
                return f.read()
        mp3 = asyncio.run(self._baixar(pronuncia(texto)))
        if not mp3:
            raise RuntimeError("o serviço de voz não devolveu áudio")
        pcm = mp3_para_pcm(mp3)
        if self.efeito:
            pcm = efeito_radio(pcm)
        dados = para_wav(pcm)
        if cacheavel:
            try:
                os.makedirs(PASTA_CACHE, exist_ok=True)
                with open(caminho, "wb") as f:
                    f.write(dados)
            except OSError:
                pass
        return dados

    def falar(self, texto):
        if not self.ok:
            return False
        tocar_wav(self.gerar_wav(texto))
        return True


VOZES_EN = [
    ("en-GB-RyanNeural", "Ryan - British, male"),
    ("en-GB-ThomasNeural", "Thomas - British, male"),
    ("en-US-AndrewNeural", "Andrew - American, male"),
    ("en-US-GuyNeural", "Guy - American, male"),
    ("en-AU-WilliamNeural", "William - Australian, male"),
    ("en-GB-SoniaNeural", "Sonia - British, female"),
]


def ouvir_vozes(nome_piloto="", velocidade="+8%"):
    """Toca a mesma frase em cada voz sugerida, para escolher."""
    if not garantir_dependencias():
        print("Sem os componentes da voz neural; não dá para ouvir as opções.")
        return
    nome = f"{nome_piloto}, " if nome_piloto else ""
    frase = f"{nome}Safety Car na pista. Bom momento para parar. Box, box!"
    for i, (voz, desc) in enumerate(VOZES_SUGERIDAS, 1):
        print(f"\n  Voz {i}: {desc}\n         ({voz})", flush=True)
        try:
            VozNeural(voz, velocidade, efeito=True).falar(frase)
        except Exception as e:  # noqa: BLE001
            print(f"         indisponível agora: {e}")
    print("\n  Para comparar: a voz 1 sem o efeito de rádio", flush=True)
    try:
        VozNeural(VOZES_SUGERIDAS[0][0], velocidade, efeito=False).falar(frase)
    except Exception as e:  # noqa: BLE001
        print(f"         indisponível agora: {e}")
    print("\nPara escolher, abra o config.json no Bloco de Notas e troque o valor de \"voz_neural\"")
    print("pelo código entre parênteses (por exemplo: \"en-US-AndrewMultilingualNeural\").")
    print("Para tirar o efeito de rádio: \"voz_efeito_radio\": false")
