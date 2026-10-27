# -*- coding: utf-8 -*-
"""
Conversa por voz com o engenheiro, pelo microfone do notebook (ou do fone conectado nele). Tudo offline e grátis.

Como funciona:
  1. Fica escutando só a palavra de ativação ("engenheiro") com o Vosk, que é leve.
     - "engenheiro, pneus" (palavra + comando curto) responde na hora.
  2. Depois de "engenheiro" sozinho, ou do botão de falar (controle ou painel), toca um bipe e grava a sua frase.
  3. A frase é transcrita pelo Whisper (entende frases inteiras; roda no notebook) ou, se ele não estiver
     instalado, pelo próprio Vosk em modo livre. A resposta vem da conversa (conversa.py).
Enquanto o próprio engenheiro está falando, o microfone é ignorado (para ele não se ouvir).
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.request
import zipfile

import idioma
from idioma import L as tr

CONGELADO = getattr(sys, "frozen", False)
AQUI = os.path.dirname(sys.executable) if CONGELADO else os.path.dirname(os.path.abspath(__file__))
PASTA_MODELOS = os.path.join(AQUI, "modelos")
MODELOS_VOSK = {"pt": "vosk-model-small-pt-0.3", "en": "vosk-model-small-en-us-0.15"}
PALAVRA_PADRAO = {"pt": "engenheiro", "en": "engineer"}


def _lang():
    return "en" if idioma.en() else "pt"

# palavra falada (sem acento) -> comando curto (respondido na hora, sem transcrição)
COMANDOS = [
    # vem primeiro: "teste de rádio" não pode cair em "clima"/"situação"
    (("teste de radio", "radio teste", "teste", "testando", "alto e claro", "me ouve", "ta me ouvindo",
      "esta me ouvindo", "radio check", "loud and clear", "can you hear me", "do you hear me", "testing"),
     "teste_radio"),
    (("rivais", "rivals", "adversarios"), "rivais"),
    (("situacao", "posicao", "diferenca", "como estou", "situation", "position", "gap", "gaps"), "situacao"),
    (("pneu", "pneus", "desgaste", "tyre", "tyres", "tire", "tires", "wear"), "pneus"),
    (("combustivel", "gasolina", "fuel"), "combustivel"),
    (("estrategia", "parar", "parada", "box", "strategy", "pit"), "estrategia"),
    (("repete", "repetir", "de novo", "repeat", "say again"), "repetir"),
    (("clima", "chuva", "previsao", "weather", "rain", "forecast"), "clima"),
    (("silencio", "quiet", "silence"), "silencio"),
    (("motor", "pecas", "peca", "turbo", "bateria", "engine", "parts", "battery"), "pecas"),
    (("pode falar", "talk to me", "radio on"), "falar"),
]
VOCABULARIO = {
    "pt": ["situação", "posição", "diferença", "como", "estou", "pneu", "pneus", "desgaste",
           "combustível", "gasolina", "estratégia", "parar", "parada", "box", "repete", "repetir",
           "de", "novo", "clima", "chuva", "previsão", "silêncio", "pode", "falar", "motor", "peças",
           "peça", "turbo", "bateria", "teste", "rádio", "testando", "alto", "claro", "me", "ouve", "rivais"],
    "en": ["situation", "position", "gap", "gaps", "tire", "tires", "wear", "fuel", "strategy", "pit", "box",
           "repeat", "say", "again", "weather", "rain", "forecast", "quiet", "silence", "talk", "to", "me",
           "radio", "on", "engine", "parts", "turbo", "battery", "check", "loud", "and", "clear", "testing",
           "can", "you", "hear", "rivals"],
}
PILOTOS_DICA = ("Verstappen, Hadjar, Leclerc, Hamilton, Norris, Piastri, Russell, Antonelli, Alonso, Stroll, Albon, "
                "Sainz, Lawson, Lindblad, Ocon, Bearman, Hulkenberg, Bortoleto, Gasly, Colapinto, Bottas, Pérez")
DICA_WHISPER = {
    "pt": ("Engenheiro, quanto falta pro carro da frente? O pneu aguenta até o fim? Quando eu paro? Box. "
           "Safety Car. Overtake. Desgaste. Combustível. Setor. Traseira. Dianteira. " + PILOTOS_DICA + "."),
    "en": ("Engineer, what's the gap to the car ahead? Will the tyres make it to the end? When do I pit? Box. "
           "Safety Car. Overtake. Tyre wear. Fuel. Sector. Understeer. Oversteer. " + PILOTOS_DICA + "."),
}


def sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def interpretar(texto):
    """Devolve o comando curto encontrado na frase (ou None)."""
    import re
    t = " " + " ".join(re.sub(r"[^a-z0-9 ]+", " ", sem_acento(texto)).split()) + " "
    for palavras, cmd in COMANDOS:
        if any(f" {p} " in t for p in palavras):
            return cmd
    return None


def _pip(*pacotes):
    if CONGELADO:
        return False
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *pacotes],
                       check=True, timeout=900)
        import importlib
        importlib.invalidate_caches()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[MICROFONE] Não consegui instalar {', '.join(pacotes)} ({e}).")
        return False


def _garantir_dependencias():
    try:
        import sounddevice  # noqa: F401
        import vosk  # noqa: F401
        return True
    except ImportError:
        pass
    print("[MICROFONE] Instalando o reconhecimento de voz (só na primeira vez)...", flush=True)
    if not _pip("vosk>=0.3.45", "sounddevice>=0.4"):
        return False
    try:
        import sounddevice  # noqa: F401,F811
        import vosk  # noqa: F401,F811
        return True
    except ImportError:
        return False


def _garantir_modelo(lang="pt"):
    nome = MODELOS_VOSK[lang]
    destino = os.path.join(PASTA_MODELOS, nome)
    if os.path.isdir(destino):
        return destino
    os.makedirs(PASTA_MODELOS, exist_ok=True)
    arq = os.path.join(PASTA_MODELOS, nome + ".zip")
    print(f"[MICROFONE] Baixando o modelo de voz '{nome}' (~30-40 MB, só na primeira vez)...", flush=True)
    urllib.request.urlretrieve(f"https://alphacephei.com/vosk/models/{nome}.zip", arq)
    with zipfile.ZipFile(arq) as z:
        z.extractall(PASTA_MODELOS)
    os.remove(arq)
    return destino


class Transcritor:
    """Whisper (faster-whisper) rodando no notebook. Se não der para instalar/carregar, fica desligado."""

    def __init__(self, tamanho="small"):
        self.tamanho = tamanho
        self.modelo = None
        self.erro = None

    def carregar(self):
        try:
            try:
                from faster_whisper import WhisperModel
            except ImportError:
                print("[MICROFONE] Instalando o reconhecimento de frases (Whisper), só na primeira vez...", flush=True)
                if not _pip("faster-whisper>=1.0"):
                    raise
                from faster_whisper import WhisperModel
            print(f"[MICROFONE] Carregando o reconhecimento de frases (Whisper '{self.tamanho}'). "
                  f"Na primeira vez ele baixa o modelo.", flush=True)
            os.makedirs(PASTA_MODELOS, exist_ok=True)
            self.modelo = WhisperModel(self.tamanho, device="cpu", compute_type="int8",
                                       download_root=os.path.join(PASTA_MODELOS, "whisper"))
            print("[MICROFONE] Whisper pronto: pode falar frases inteiras.", flush=True)
        except Exception as e:  # noqa: BLE001
            self.modelo = None
            self.erro = str(e)
            print(f"[MICROFONE] Whisper indisponível ({e}). Uso o Vosk para as frases.", flush=True)

    def transcrever(self, audio_16k):
        lang = _lang()
        segs, _ = self.modelo.transcribe(audio_16k, language=lang, beam_size=1, vad_filter=False,
                                         initial_prompt=DICA_WHISPER[lang], condition_on_previous_text=False)
        return " ".join(s.text for s in segs).strip()


class Microfone:
    def __init__(self, cfg, ao_comando, radio, ao_texto=None):
        self.ao_comando = ao_comando
        self.ao_texto = ao_texto
        self.radio = radio
        self.lang = _lang()
        palavra = sem_acento(cfg.get("microfone_palavra_ativacao") or PALAVRA_PADRAO[self.lang])
        if palavra in PALAVRA_PADRAO.values():         # a palavra padrão acompanha o idioma
            palavra = PALAVRA_PADRAO[self.lang]
        self.palavra = palavra
        self.segundos_janela = float(cfg.get("microfone_segundos_apos_botao", 5))
        modelo_frases = str(cfg.get("microfone_frases", "whisper-small"))
        self.transcritor = None
        if modelo_frases.startswith("whisper"):
            self.transcritor = Transcritor(modelo_frases.split("-", 1)[1] if "-" in modelo_frases else "small")
        self._gravar_ate = 0.0       # gravando a frase até este instante (no máximo)
        self._ignorar_ate = 0.0      # não grava o próprio bip de confirmação
        self.som_escuta = bool(cfg.get("microfone_som_escuta", True))
        self.pronto = False
        self.erro = None
        self.estado = "desligado"    # para o painel: desligado / escutando / gravando / pensando

    def iniciar(self):
        threading.Thread(target=self._preparar_e_ouvir, daemon=True).start()

    def ativar_escuta(self):
        """Botão de falar: grava a próxima frase, sem precisar dizer a palavra de ativação."""
        if not self.pronto:
            self.radio.falar(tr("O microfone ainda não está pronto.", "The microphone isn't ready yet."),
                             1, "mic-nao-pronto", 5)
            return
        self._comecar_gravacao()

    def _comecar_gravacao(self):
        self._ignorar_ate = time.monotonic() + 0.35
        self._gravar_ate = time.monotonic() + max(6.0, self.segundos_janela + 3)
        self.estado = "gravando"
        self._bip()

    def _bip(self):
        """Bip do rádio de equipe: avisa que o engenheiro ouviu e vai responder."""
        if not self.som_escuta:
            return
        try:
            import voz
            voz.tocar_som_escuta()
        except Exception:  # noqa: BLE001
            pass

    def _preparar_e_ouvir(self):
        try:
            if not _garantir_dependencias():
                return
            caminho = _garantir_modelo(self.lang)
            import numpy as np
            import sounddevice as sd
            import vosk
            vosk.SetLogLevel(-1)
            modelo = vosk.Model(caminho)
            dispositivo = sd.query_devices(kind="input")
            taxa = int(dispositivo["default_samplerate"])
            gramatica = json.dumps(VOCABULARIO[self.lang] + [self.palavra, "[unk]"], ensure_ascii=False)
            rec = vosk.KaldiRecognizer(modelo, taxa, gramatica)
            self._modelo_vosk, self._taxa = modelo, taxa
            if self.transcritor is not None:
                threading.Thread(target=self.transcritor.carregar, daemon=True).start()
            fila = queue.Queue()

            def captura(dados, _frames, _tempo, _status):
                fila.put(bytes(dados))

            with sd.RawInputStream(samplerate=taxa, blocksize=int(taxa * 0.1), dtype="int16", channels=1,
                                   callback=captura):
                self.pronto = True
                self.estado = "escutando"
                print(f"[MICROFONE] Ouvindo pelo microfone: {dispositivo['name']}. "
                      f"Diga \"{self.palavra}\" e faça a pergunta, ou aperte o botão de falar.", flush=True)
                falando_antes = False
                gravacao, falou, silencio, inicio = [], False, 0.0, 0.0
                frase = []                 # áudio da frase atual (para quando você fala tudo de uma vez)
                while True:
                    dados = fila.get()
                    if self.radio.esta_falando():          # não escutar a própria voz do engenheiro
                        falando_antes = True
                        continue
                    if falando_antes:
                        rec.Reset()
                        frase = []
                        falando_antes = False
                    agora = time.monotonic()
                    if agora < self._ignorar_ate:
                        continue
                    if agora < self._gravar_ate:
                        # ---- gravando a frase: para depois de ~1 s de silêncio ----
                        if not gravacao:
                            falou, silencio, inicio = False, 0.0, agora
                        amostra = np.frombuffer(dados, dtype=np.int16)
                        gravacao.append(amostra)
                        nivel = float(np.sqrt(np.mean((amostra.astype(np.float32) / 32768) ** 2))) if amostra.size else 0
                        if nivel > 0.02:
                            falou, silencio = True, 0.0
                        else:
                            silencio += amostra.size / taxa
                        if (falou and silencio >= 1.0) or (not falou and agora - inicio > 4.5):
                            self._gravar_ate = 0.0
                        continue
                    if gravacao:
                        audio = np.concatenate(gravacao)
                        gravacao = []
                        rec.Reset()
                        if falou:
                            self.estado = "pensando"
                            threading.Thread(target=self._transcrever_e_responder, args=(audio,), daemon=True).start()
                        else:
                            self.estado = "escutando"
                        continue
                    frase.append(np.frombuffer(dados, dtype=np.int16))
                    if len(frase) > 120:           # guarda no máximo ~12 s
                        frase = frase[-120:]
                    if rec.AcceptWaveform(dados):
                        texto = json.loads(rec.Result()).get("text", "")
                        audio_frase = np.concatenate(frase) if frase else None
                        frase = []
                        self._tratar(texto, audio_frase)
        except Exception as e:  # noqa: BLE001
            self.erro = str(e)
            self.estado = "desligado"
            print(f"[MICROFONE] Desligado: {e}")

    def _transcrever_e_responder(self, audio):
        try:
            texto = ""
            if self.transcritor is not None and self.transcritor.modelo is not None:
                import numpy as np
                x = audio.astype(np.float32) / 32768
                if self._taxa != 16000:          # o Whisper trabalha em 16 kHz
                    n = int(len(x) * 16000 / self._taxa)
                    x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
                texto = self.transcritor.transcrever(x)
            else:
                import vosk
                livre = vosk.KaldiRecognizer(self._modelo_vosk, self._taxa)
                livre.AcceptWaveform(audio.tobytes())
                texto = json.loads(livre.FinalResult()).get("text", "")
            texto = texto.strip()
            # tira a palavra de ativação do começo ("Engenheiro, quanto falta...")
            palavras = texto.split()
            if palavras and sem_acento(palavras[0]).strip(",.!?:") == self.palavra:
                texto = " ".join(palavras[1:]).lstrip(",. ")
            print(f"[MICROFONE] Ouvi: \"{texto}\"", flush=True)
            if not texto:
                self.ao_comando("nao_entendi")
            elif self.ao_texto is not None:
                self.ao_texto(texto)
            else:
                self.ao_comando(interpretar(texto) or "nao_entendi")
        except Exception as e:  # noqa: BLE001
            print(f"[MICROFONE] Erro ao entender a frase: {e}")
        finally:
            self.estado = "escutando"

    def _tratar(self, texto, audio_frase=None):
        bruto = sem_acento(texto)
        desconhecidas = bruto.count("[unk]")
        t = bruto.replace("[unk]", " ")
        if f" {self.palavra} " not in f" {' '.join(t.split())} ":
            return
        resto = " ".join(f" {t} ".replace(f" {self.palavra} ", " ").split())
        cmd = interpretar(resto) if resto else None
        if cmd and desconhecidas == 0:
            print(f"[MICROFONE] Ouvi: \"{texto}\" -> {cmd}", flush=True)
            self._bip()
            self.ao_comando(cmd)
        elif (desconhecidas or resto) and audio_frase is not None and audio_frase.size > self._taxa * 0.8:
            # falou "engenheiro, ..." e a pergunta inteira de uma vez: transcreve a frase toda
            self._bip()
            self.estado = "pensando"
            threading.Thread(target=self._transcrever_e_responder, args=(audio_frase,), daemon=True).start()
        else:
            self._comecar_gravacao()      # só a palavra de ativação: grava a pergunta em seguida
