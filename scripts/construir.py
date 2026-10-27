# -*- coding: utf-8 -*-
"""Gera o Engenheiro.exe (PyInstaller) e, se pedido, o zip para a página de versões.

Uso (na pasta do projeto, com as bibliotecas instaladas):
    python scripts/construir.py                 -> dist/Engenheiro/ (Engenheiro.exe + _internal)
    python scripts/construir.py --pacote        -> também cria dist/Engenheiro-<versão>-windows.zip
    python scripts/construir.py --nesta-pasta   -> coloca o Engenheiro.exe e o _internal na pasta do projeto

Bibliotecas: pip install pyinstaller edge-tts soundfile numpy sounddevice vosk faster-whisper
O GitHub Actions (.github/workflows/release.yml) usa este mesmo script.
"""
import os
import shutil
import subprocess
import sys
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import versao  # noqa: E402

NOME = "Engenheiro"
EXE = NOME + (".exe" if os.name == "nt" else "")

MODULOS = ["engenheiro", "painel", "voz", "microfone", "conversa", "estrategia", "analise", "relatorio",
           "falas", "idioma", "vigia", "simulador", "versao"]
# módulos da biblioteca padrão que o código da pasta pode usar numa versão futura sem gerar o programa de novo
PADRAO = ["locale", "csv", "statistics", "difflib", "unicodedata", "wave", "array", "asyncio", "heapq", "bisect",
          "hashlib", "zipfile", "urllib.request", "http.server", "socketserver", "random", "struct", "queue",
          "subprocess", "ctypes", "webbrowser", "base64", "tempfile", "shutil", "glob", "dataclasses",
          "fractions", "decimal", "calendar", "uuid", "html", "xml.etree.ElementTree", "email", "gzip",
          "sqlite3", "concurrent.futures", "logging", "pprint"]
COLETAR = ["vosk", "faster_whisper", "ctranslate2", "tokenizers", "soundfile", "sounddevice", "edge_tts", "av"]

# arquivos que vão junto do programa no zip (sem config.json, sessões ou acertos de ninguém)
ARQUIVOS_PACOTE = ["painel.html", "relatorio_modelo.html", "voz.ps1", "icone.ico", "LICENSE.txt",
                   "THIRD_PARTY_NOTICES.txt", "pacote/LEIA-ME.txt", "pacote/README.txt"]


def gerar():
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
            "--name", NOME, "--icon", os.path.join(RAIZ, "icone.ico"),
            "--distpath", os.path.join(RAIZ, "dist"), "--workpath", os.path.join(RAIZ, "build"),
            "--specpath", os.path.join(RAIZ, "build")]
    for m in COLETAR:
        args += ["--collect-all", m]
    for m in MODULOS + PADRAO:
        args += ["--hidden-import", m]
    args += ["--collect-submodules", "f1_types", os.path.join(RAIZ, "app.py")]
    print("Gerando o programa com o PyInstaller...", flush=True)
    subprocess.run(args, cwd=RAIZ, check=True)
    return os.path.join(RAIZ, "dist", NOME)


def pacote(pasta):
    for arq in ARQUIVOS_PACOTE:
        shutil.copy2(os.path.join(RAIZ, arq), os.path.join(pasta, os.path.basename(arq)))
    mapas = os.path.join(pasta, "mapas")
    os.makedirs(mapas, exist_ok=True)
    for arq in os.listdir(os.path.join(RAIZ, "mapas")):
        if arq == "curvas.json" or (arq.startswith("pista_") and arq.endswith(".json")):
            shutil.copy2(os.path.join(RAIZ, "mapas", arq), mapas)
    destino = os.path.join(RAIZ, "dist", f"{NOME}-{versao.VERSAO}-windows.zip")
    if os.path.exists(destino):
        os.remove(destino)
    print(f"Compactando {os.path.basename(destino)}...", flush=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for raiz, _, arquivos in os.walk(pasta):
            for arq in arquivos:
                caminho = os.path.join(raiz, arq)
                z.write(caminho, os.path.join(NOME, os.path.relpath(caminho, pasta)))
    print(f"Pronto: {destino}")
    return destino


def nesta_pasta(pasta):
    interno = os.path.join(RAIZ, "_internal")
    if os.path.isdir(interno):
        shutil.rmtree(interno)
    shutil.move(os.path.join(pasta, "_internal"), interno)
    shutil.move(os.path.join(pasta, EXE), os.path.join(RAIZ, EXE))
    shutil.rmtree(os.path.join(RAIZ, "dist"), ignore_errors=True)
    print(f"Pronto: {os.path.join(RAIZ, EXE)}")


def main():
    pasta = gerar()
    shutil.rmtree(os.path.join(RAIZ, "build"), ignore_errors=True)
    if "--pacote" in sys.argv:
        pacote(pasta)
    if "--nesta-pasta" in sys.argv:
        nesta_pasta(pasta)


if __name__ == "__main__":
    main()
