# -*- coding: utf-8 -*-
"""Nome, versão e créditos do app (aparecem na tela "Sobre" e no pacote de versões)."""

NOME = "Engenheiro"
VERSAO = "1.2.0"
SUBTITULO = ("engenheiro de corrida por voz para o F1 25 (não oficial)",
             "a free voice race engineer for F1 25 (unofficial)")
AUTOR = "Yohan Vieira"
USUARIO_GITHUB = "yohanfv"
LINK_GITHUB = f"https://github.com/{USUARIO_GITHUB}/engenheiro" if USUARIO_GITHUB else ""
LINK_DOACAO = "https://ko-fi.com/yohanfv"
AVISO = ("Projeto de fã, não oficial. Sem ligação com a Formula 1, a FIA, a EA ou a Codemasters. "
         "F1 e FORMULA 1 são marcas da Formula One Licensing B.V.",
         "Unofficial fan project. Not affiliated with Formula 1, the FIA, EA or Codemasters. "
         "F1 and FORMULA 1 are trademarks of Formula One Licensing B.V.")
TERCEIROS = [
    # (nome, licença, uso)
    ("Pits n' Giggles (Ashwin Natarajan)", "MIT", ("leitura dos pacotes UDP", "UDP packet parsing")),
    ("TracingInsights", "Apache 2.0", ("números oficiais das curvas e tempo de box", "official corner numbers and pit loss")),
    ("Vosk", "Apache 2.0", ("palavra de ativação e comandos", "wake word and commands")),
    ("faster-whisper / CTranslate2", "MIT", ("reconhecimento de frases", "speech recognition")),
    ("OpenAI Whisper models", "MIT", ("modelos de fala", "speech models")),
    ("edge-tts", "LGPL-3.0", ("voz neural (serviço online da Microsoft)", "neural voice (Microsoft online service)")),
    ("NumPy, SoundFile, sounddevice, PyAV", "BSD / MIT", ("áudio", "audio")),
    ("PyInstaller", "GPL-2.0 + bootloader exception", ("gera o executável", "builds the executable")),
]
