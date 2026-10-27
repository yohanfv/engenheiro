<p align="center"><img src="docs/icon.png" width="96" alt="Engenheiro icon"></p>

<h1 align="center">Engenheiro</h1>
<p align="center"><b>A free voice race engineer for F1 25</b> · unofficial fan project · Windows</p>

<p align="center">
  <a href="https://github.com/yohanfv/engenheiro/releases/latest"><b>Download</b></a> ·
  <a href="README.pt-BR.md">Português</a> ·
  <a href="CHANGELOG.md">Changelog</a> ·
  <a href="https://github.com/yohanfv/engenheiro/issues">Report a problem</a> ·
  <a href="https://ko-fi.com/yohanfv">Support ☕</a>
</p>

<p align="center"><img src="docs/dashboard.jpg" alt="Engenheiro live dashboard during a race"></p>

Engenheiro (Portuguese for *engineer*) listens to the F1 25 telemetry and talks to you over the radio while you drive:
gaps, tyre wear, Safety Car calls, rain, "box, box", "defend!", rival strategy, retirements and more. You can talk
back with your microphone, your controller buttons or by typing. It works with F1 25 on **PS5, Xbox or PC**, in
**English or Brazilian Portuguese**, with no account, no subscription and no paid AI.

## Features

- **Race radio:** lap times and sector deltas, gaps ahead and behind (calculated like official timing), overtakes
  ("Great move on Leclerc!"), places lost and why, "Overtake available, attack", "defend!", final laps and result.
- **Strategy from your real tyre wear:** compares no-stop, one-stop and two-stop plans with your remaining tyre
  sets and the real pit loss of each track, calls "box, box" on the right lap and re-plans under a Safety Car.
- **Watches your rivals:** retirements (who, where and why), slow or stopped cars, contact, rival wing damage,
  drivers losing time, when the cars around you should pit, undercut and overcut chances.
- **Ask anything:** "what's the gap to Verstappen?", "has Leclerc pitted?", "will the tyres make it to the end?",
  "I have understeer on entry" (setup advice). Say **"Engineer"** and your question; a short team-radio beep
  confirms he heard you. Speech recognition runs on your PC.
- **Live dashboard:** official-style track map with corner numbers and sector colours, timing tower, your car,
  tyre temperatures and wear, power unit wear, radio log. Open it on your phone too.
- **Practice analysis and reports:** pace vs the AI, where each tyre overheats, setup suggestions, a race plan,
  and a corner-by-corner report of where you lose time.
- **Demo mode:** see everything working without the game (simulated race, qualifying or practice).

<p align="center"><img src="docs/report.jpg" width="80%" alt="Corner-by-corner report"></p>

## Download and install

1. Download the latest `Engenheiro-x.y.z-windows.zip` from the [Releases](https://github.com/yohanfv/engenheiro/releases/latest) page.
2. Unzip it to a normal folder, for example `C:\Engenheiro` (avoid OneDrive folders).
3. Open **Engenheiro.exe**.
   - Windows may show *"Windows protected your PC"* because the app is not code-signed (signing certificates cost
     money and this is a free hobby project). Click **More info → Run anyway**. The full source code is in this
     repository if you want to check or build it yourself.
   - When Windows Firewall asks, allow it on **Private networks**, otherwise the game data can't reach the app.
4. A welcome screen asks for your language and shows the IP address to put in the game.

Requirements: Windows 10 or 11 on the same network as your console (or the PC running the game) and an internet
connection the first time (the voice uses Microsoft's online voices; the speech models are downloaded once).

## Game settings

In F1 25: **Settings → Telemetry Settings**

| Setting | Value |
| --- | --- |
| UDP Telemetry | On |
| UDP Broadcast Mode | Off |
| UDP IP Address | the IP shown by Engenheiro (playing on the same PC? `127.0.0.1`) |
| UDP Port | 20777 |
| UDP Send Rate | 20 Hz |
| UDP Format | 2025 (or 2026 with the 2026 Season Pack) |

Then start any session. The dashboard shows **game connected** and the engineer says *"Radio check. I'm with you."*

**Controller buttons (optional):** in F1 25, Settings → Controls → edit mapping, assign *UDP Action 1-7*:
1 situation · 2 tyres and fuel · 3 strategy · 4 repeat · 5 talk · 6 radio check · 7 rival strategy.

**SimHub at the same time:** only one program can use port 20777. Engenheiro forwards a copy of the data to port
20778, so set SimHub's game port to 20778.

**Radio on your phone:** open `http://YOUR-PC-IP:8080` on your phone, tap *Play radio here* and use your earbuds.
You can turn this off in Settings (dashboard only on this PC).

**Updates:** when a new version is out, a green **⬆ v…** button appears at the top of the dashboard. Download the
new zip and extract it over the same folder; your settings, sessions and setups are kept. (The check only asks
GitHub for the latest version number and can be turned off in Settings.)

## Troubleshooting

| Problem | Fix |
| --- | --- |
| "no game data" | Check the IP and port in the game, allow the app on Private networks in Windows Firewall, and make sure the PC and the console are on the same network. |
| "Port 20777 is already in use" | Close SimHub or another copy of the app, or set SimHub to port 20778. |
| No voice | Check the internet connection and volume. Without internet it falls back to the Windows voice. |
| Microphone does nothing | Windows Settings → Privacy & security → Microphone → let desktop apps use it. Wait for the first download. |
| PC slows down with the mic on | Settings → Microphone → Recognition: "Whisper light" or "Basic". |
| Anything else | Open an [issue](https://github.com/yohanfv/engenheiro/issues) and attach `engenheiro.log` from the app folder. |

## Build from source

Requires Windows and Python 3.12.

```
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt pyinstaller
python engenheiro.py                         # run from source (dashboard opens in the browser)
python simulador.py corrida --incidentes     # in a second window: a simulated race, no game needed
python scripts/construir.py --pacote         # dist/Engenheiro-<version>-windows.zip
```

Or just double-click `scripts\gerar_executavel.bat`, which does all of the above and puts `Engenheiro.exe` in the
project folder. Releases are built automatically by GitHub Actions (`.github/workflows/release.yml`): bump
`VERSAO` in `versao.py`, add the version to `CHANGELOG.md` and run the **Build release** workflow.

### Project layout

| Path | What it is |
| --- | --- |
| `engenheiro.py` | Main program: receives the UDP telemetry, tracks the session, decides what to say |
| `app.py` | Windows entry point (`Engenheiro.exe`): opens the dashboard window |
| `vigia.py`, `estrategia.py` | Track watch (retirements, rivals, undercuts) and pit strategy |
| `voz.py`, `microfone.py`, `conversa.py` | Voice, speech recognition and answers to free questions |
| `painel.py`, `painel.html` | Live dashboard (local web server + page) |
| `analise.py`, `relatorio.py` | Practice analysis and corner-by-corner report |
| `falas.py`, `idioma.py` | Radio phrases and the English / Portuguese switch |
| `simulador.py` | Fake F1 25 session for testing and the demo mode |
| `f1_types/` | UDP packet classes (from Pits n' Giggles) |
| `mapas/` | Track outlines, official corner numbers and pit loss |
| `pacote/` | Quick guides that go inside the release zip |
| `scripts/` | Build scripts and helpers |

The code and comments are in Portuguese; the app itself is fully bilingual.

## Support the project

Engenheiro is free and always will be: nothing in the app is locked or paid. If it makes your races better and you
want to say thanks, you can leave a tip on [Ko-fi](https://ko-fi.com/yohanfv). Bug reports, ideas and a ⭐ on this
repository help just as much.

## Credits

Created by **Yohan Vieira**. Built with the help of Claude (Anthropic).

- UDP packet parsing based on [Pits n' Giggles](https://github.com/ashwin-nat/pits-n-giggles) by Ashwin Natarajan (MIT).
- Official corner numbers and pit loss times from [TracingInsights](https://tracinginsights.com/) public data (Apache 2.0).
- Speech: [Vosk](https://alphacephei.com/vosk/) (Apache 2.0), [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
  and OpenAI Whisper models (MIT), [edge-tts](https://github.com/rany2/edge-tts) (LGPL-3.0).

Full details in [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt). Engenheiro itself is released under the
[MIT License](LICENSE.txt).

## Disclaimer

Unofficial fan project. Not affiliated with, endorsed or sponsored by Formula 1, the FIA, Electronic Arts or
Codemasters. F1 and FORMULA 1 are trademarks of Formula One Licensing B.V.; they are used here only to describe
which game the app works with.
