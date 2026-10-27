# -*- coding: utf-8 -*-
"""
Engenheiro em janela própria (é o que o executável "Engenheiro.exe" roda).

- Sobe o engenheiro (telemetria, voz, microfone, painel) em segundo plano.
- Abre o painel numa janela própria do Microsoft Edge (modo aplicativo: sem abas e sem barra de endereço).
- Fechou a janela, o engenheiro salva a sessão e encerra.
- Tudo o que antes aparecia na janela preta fica em engenheiro.log, na mesma pasta.
"""

import os
import subprocess
import sys
import threading
import time

CONGELADO = getattr(sys, "frozen", False)
AQUI = os.path.dirname(sys.executable) if CONGELADO else os.path.dirname(os.path.abspath(__file__))


def _preparar_log():
    """Sem janela preta não há onde imprimir: tudo vai para engenheiro.log."""
    if CONGELADO or sys.stdout is None or "--log" in sys.argv:
        caminho = os.path.join(AQUI, "engenheiro.log")
        try:
            if os.path.exists(caminho) and os.path.getsize(caminho) > 2_000_000:
                os.replace(caminho, caminho + ".antigo")
        except OSError:
            pass
        arq = open(caminho, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = arq
        print("\n" + "=" * 64 + f"\n{time.strftime('%d/%m/%Y %H:%M:%S')}  Engenheiro iniciado")


# módulos do próprio engenheiro: no executável eles são lidos da pasta (os .py ao lado do .exe), não da cópia
# guardada dentro do programa. Assim uma versão nova é só extrair o zip por cima, sem gerar o .exe de novo.
MODULOS_DA_PASTA = {"engenheiro", "painel", "voz", "microfone", "conversa", "estrategia", "analise", "relatorio",
                    "falas", "idioma", "vigia", "f1_types", "simulador", "versao"}


class _CodigoDaPasta:
    """Procura os módulos do engenheiro primeiro na pasta do programa."""

    def find_spec(self, nome, caminho=None, alvo=None):
        if nome.split(".", 1)[0] not in MODULOS_DA_PASTA:
            return None
        import importlib.machinery
        onde = caminho if "." in nome else [AQUI]
        try:
            return importlib.machinery.PathFinder.find_spec(nome, onde)
        except Exception:  # noqa: BLE001
            return None


def _usar_codigo_da_pasta():
    if not CONGELADO:
        return
    if all(os.path.exists(os.path.join(AQUI, m + ".py")) or os.path.isdir(os.path.join(AQUI, m))
           for m in ("engenheiro", "painel", "f1_types")):
        sys.meta_path.insert(0, _CodigoDaPasta())
        print("[APP] Usando o código da pasta (versões novas: é só extrair o zip por cima).")
    else:
        print("[APP] Código da pasta não encontrado; usando a cópia de dentro do programa.")


def _aviso(titulo, texto):
    print(f"[{titulo}] {texto}")
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, texto, titulo, 0x40)
        except Exception:  # noqa: BLE001
            pass


def _achar_navegador():
    candidatos = []
    for var in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(var)
        if base:
            candidatos += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                           os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    for c in candidatos:
        if os.path.exists(c):
            return c
    for nome in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
        for pasta in os.environ.get("PATH", "").split(os.pathsep):
            c = os.path.join(pasta, nome)
            if os.path.exists(c):
                return c
    return None


def _abrir_janela(url):
    """Abre o painel numa janela de aplicativo e devolve o processo (ou None se não achou o Edge/Chrome)."""
    nav = _achar_navegador()
    if not nav:
        return None
    perfil = os.path.join(AQUI, "dados_janela")     # perfil separado: a janela é um processo só nosso
    cmd = [nav, f"--app={url}/?app=1", f"--user-data-dir={perfil}", "--window-size=1400,860",
           "--no-first-run", "--no-default-browser-check", "--disable-features=Translate,msEdgeSidebarV2",
           "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
           "--disable-backgrounding-occluded-windows"]
    try:
        return subprocess.Popen(cmd)
    except OSError as e:
        print(f"[JANELA] Não consegui abrir a janela: {e}")
        return None


def main():
    _preparar_log()
    sys.path.insert(0, AQUI)
    _usar_codigo_da_pasta()
    try:
        import engenheiro
    except Exception as e:  # noqa: BLE001   (ex.: uma versão nova que precisa de biblioteca nova)
        import traceback
        traceback.print_exc()
        if not CONGELADO:
            raise
        sys.meta_path[:] = [f for f in sys.meta_path if not isinstance(f, _CodigoDaPasta)]
        sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != os.path.abspath(AQUI)]
        sys.path_importer_cache.clear()
        for m in [m for m in sys.modules if m.split(".", 1)[0] in MODULOS_DA_PASTA]:
            sys.modules.pop(m, None)
        print(f"[APP] O código da pasta não abriu ({e}); usando a cópia de dentro do programa.")
        _aviso("Engenheiro", "Os arquivos .py desta pasta precisam de um programa mais novo: baixe a versão mais recente "
                                "na página do projeto ou rode o scripts\\gerar_executavel.bat. "
                                "Por enquanto vou abrir a versão de dentro do programa.\n\n"
                                "The .py files in this folder need a newer program: download the latest version "
                                "from the project page or run scripts\\gerar_executavel.bat. "
                                "For now the built-in version will open.")
        import engenheiro

    args = ["--janela", "--sem-navegador"] + [a for a in sys.argv[1:] if a.startswith("--")]
    motor = threading.Thread(target=engenheiro.main, args=(args,), daemon=True)
    motor.start()
    engenheiro.ESTADO_APP["pronto"].wait(60)
    if engenheiro.ESTADO_APP["erro"]:
        _aviso("Engenheiro", engenheiro.ESTADO_APP["erro"])
        return
    url = engenheiro.ESTADO_APP["url"]
    if not url:
        _aviso("Engenheiro", engenheiro.tr("Não consegui abrir o painel (a porta do painel está ocupada?). "
                                              "Veja o arquivo engenheiro.log.",
                                              "Could not open the dashboard (is the dashboard port in use?). "
                                              "See the engenheiro.log file."))
        engenheiro.PARAR.set()
        motor.join(15)
        return
    proc = _abrir_janela(url)
    eng = engenheiro.ESTADO_APP["eng"]
    inicio = time.monotonic()
    if proc is None:
        import webbrowser
        webbrowser.open(url)
        _aviso("Engenheiro", engenheiro.tr("Não achei o Microsoft Edge, então o painel abriu no navegador. "
                                              "Para fechar o engenheiro, use o botão Fechar nas Configurações do painel.",
                                              "Microsoft Edge was not found, so the dashboard opened in your browser. "
                                              "To close the engineer, use the Close button in the dashboard Settings."))
    # espera: a janela fechar, ou o botão "Fechar o engenheiro", ou o painel parar de dar sinal de vida.
    # Na primeira vez, o Edge às vezes fecha o processo que abrimos e reabre a janela em outro (perfil novo);
    # por isso, se o processo some logo no começo, passamos a vigiar só o sinal de vida da página.
    janela_edge = proc is not None      # False: abriu no navegador comum (sem sinal de vida)
    so_pelo_sinal = False               # True: o Edge trocou de processo; a janela é vigiada pelo sinal de vida
    reaberta = False
    while motor.is_alive() and not engenheiro.PARAR.is_set():
        time.sleep(0.5)
        agora = time.monotonic()
        vivo = getattr(eng, "ultimo_sinal_janela", 0)
        if proc is not None and proc.poll() is not None:
            if agora - inicio > 20:
                break                   # o usuário fechou a janela
            print("[JANELA] O Edge trocou de processo ao abrir; sigo pelo sinal de vida da página.")
            proc, so_pelo_sinal = None, True
            continue
        if so_pelo_sinal:
            if vivo and agora - vivo > 15:
                print("[JANELA] A janela foi fechada (sem sinal de vida); encerrando.")
                break
            if not vivo and not reaberta and agora - inicio > 25:
                print("[JANELA] A página não deu sinal de vida; abrindo a janela de novo.")
                reaberta = True
                proc, so_pelo_sinal, inicio = _abrir_janela(url), False, agora
            continue
        if janela_edge and proc is not None and vivo and agora - vivo > 45 and agora - inicio > 60:
            print("[JANELA] A janela parou de responder; encerrando.")
            break
    engenheiro.PARAR.set()
    motor.join(20)
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
        except OSError:
            pass
    print("Engenheiro encerrado.")


if __name__ == "__main__":
    main()
