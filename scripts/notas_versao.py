# -*- coding: utf-8 -*-
"""Texto da página de versões: a parte do CHANGELOG.md desta versão + como instalar (inglês e português)."""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
versao = sys.argv[1] if len(sys.argv) > 1 else ""
linhas, dentro = [], False
with open(os.path.join(RAIZ, "CHANGELOG.md"), encoding="utf-8") as f:
    for linha in f:
        if linha.startswith("## "):
            dentro = linha[3:].strip().split(" ")[0] == versao
            continue
        if dentro:
            linhas.append(linha.rstrip("\n"))
novidades = "\n".join(linhas).strip() or "See CHANGELOG.md."

sys.stdout.reconfigure(encoding="utf-8")
print(f"""## What's new

{novidades}

## Install

1. Download **Engenheiro-{versao}-windows.zip** below and unzip it (for example to `C:\\Engenheiro`).
2. Open **Engenheiro.exe**. If Windows SmartScreen appears: **More info → Run anyway** (the app is not code-signed).
3. Allow it on **Private networks** when the Firewall asks, then follow the welcome screen.

Updating: extract the new zip over the same folder; your settings and sessions are kept.

## Instalação (português)

1. Baixe o **Engenheiro-{versao}-windows.zip** abaixo e extraia (por exemplo em `C:\\Engenheiro`).
2. Abra o **Engenheiro.exe**. Se aparecer o SmartScreen: **Mais informações → Executar assim mesmo**.
3. Permita em **Redes privadas** quando o Firewall perguntar e siga a tela de boas-vindas.

Para atualizar: extraia o zip novo por cima da mesma pasta; suas configurações e sessões continuam lá.

## ☕ Support

Engenheiro is free and always will be. If it makes your races better, you can buy me a coffee on
[Ko-fi](https://ko-fi.com/yohanfv) — it really helps me keep improving it. Thank you!

*Unofficial fan project, not affiliated with Formula 1, the FIA, EA or Codemasters.*""")
