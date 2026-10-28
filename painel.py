# -*- coding: utf-8 -*-
"""Servidor do painel ao vivo (abre no navegador do notebook ou do celular)."""

import json
import os
import sys
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AQUI = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
ARQUIVO_PAGINA = os.path.join(AQUI, "painel.html")


def _criar_handler(eng):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # sem poluir a janela
            pass

        def _enviar(self, codigo, tipo, corpo):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            try:
                self.wfile.write(corpo)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def _json(self, dados):
            self._enviar(200, "application/json; charset=utf-8",
                         json.dumps(dados, ensure_ascii=False, default=str).encode("utf-8"))

        def _corpo_json(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}
            except (ValueError, UnicodeDecodeError):
                return {}

        def do_POST(self):
            caminho = self.path.split("?", 1)[0]
            if caminho == "/config":
                self._json(eng.salvar_config(self._corpo_json()))
                return
            if caminho == "/sair":
                self._json({"ok": True})
                import engenheiro
                engenheiro.PARAR.set()
                return
            if caminho == "/demo/iniciar":
                from urllib.parse import parse_qs, urlparse
                cen = (parse_qs(urlparse(self.path).query).get("cenario") or ["corrida"])[0]
                self._json(eng.iniciar_demo(cen))
                return
            if caminho == "/demo/parar":
                self._json(eng.parar_demo())
                return
            if caminho == "/perguntar_texto":
                texto = str(self._corpo_json().get("texto", ""))[:300]
                self._json({"resposta": eng.perguntar_texto(texto)})
                return
            m = re.match(r"^/perguntar/(situacao|pneus|estrategia|repetir|ouvir|combustivel|clima|silencio|falar|pecas)$", self.path.split("?", 1)[0])
            if m:
                eng.perguntar(m.group(1))
                self._json({"ok": True})
            else:
                self._enviar(404, "text/plain", b"")

        def do_GET(self):
            caminho = self.path.split("?", 1)[0]
            if caminho in ("/", "/index.html"):
                try:
                    with open(ARQUIVO_PAGINA, "rb") as f:
                        self._enviar(200, "text/html; charset=utf-8", f.read())
                except OSError:
                    self._enviar(404, "text/plain", b"painel.html nao encontrado")
            elif caminho == "/estado":
                self._json(eng.estado())
            elif caminho == "/mapa":
                self._json(eng.mapa())
            elif caminho == "/graficos":
                self._json(eng.graficos())
            elif caminho == "/vivo":
                import time
                eng.ultimo_sinal_janela = time.monotonic()
                self._json({"ok": True})
            elif caminho == "/config":
                self._json(eng.config_tela())
            elif caminho == "/sessoes":
                self._json(eng.sessoes_lista())
            elif caminho.startswith("/sessoes/"):
                from urllib.parse import unquote
                partes = unquote(caminho[len("/sessoes/"):]).split("/")
                dados = eng.arquivo_sessao(partes[0], partes[1]) if len(partes) == 2 else None
                if dados is None:
                    self._enviar(404, "text/plain", b"")
                else:
                    tipo = "text/html; charset=utf-8" if partes[1].endswith(".html") else "text/plain; charset=utf-8"
                    self._enviar(200, tipo, dados)
            elif caminho.startswith("/audio/"):
                m = re.match(r"^/audio/(\d+)\.wav$", caminho)
                wav = eng.radio.audios.get(int(m.group(1))) if m else None
                if wav:
                    self._enviar(200, "audio/wav", wav)
                else:
                    self._enviar(404, "text/plain", b"")
            else:
                self._enviar(404, "text/plain", b"")

    return Handler


def iniciar(eng, porta=8080, rede=True):
    """Sobe o servidor numa thread. Devolve a URL local ou None se a porta estiver ocupada.
    rede=False: só este computador abre o painel (ninguém mais da rede, nem o celular)."""
    try:
        srv = ThreadingHTTPServer(("0.0.0.0" if rede else "127.0.0.1", porta), _criar_handler(eng))
    except OSError:
        print(f"[PAINEL] A porta {porta} está ocupada; o painel não foi aberto. "
              f"Troque \"porta_painel\" no config.json.")
        return None
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://localhost:{porta}"
