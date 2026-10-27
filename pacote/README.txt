ENGENHEIRO - A FREE VOICE RACE ENGINEER FOR F1 25 (unofficial)
==============================================================

What it is
----------
A free Windows app that turns the F1 25 telemetry into a race engineer. The game sends live data
over your home network (positions, gaps, tyre wear and temperatures, fuel, weather, damage, pit
stops) and the app:
- talks to you over the "radio": lap times, gaps, tyre wear, Safety Car, rain, when to pit,
  "box, box", "defend!", results after qualifying and the race;
- calculates the best strategy (no stop, one stop or two stops) from YOUR real tyre wear;
- answers questions through the microphone ("how far is the car ahead?", "can my tyres make it?");
- shows a live dashboard with the track map, timing tower, your car and the radio messages;
- records every session and writes an automatic analysis after each practice session.

LANGUAGE: the app speaks English or Brazilian Portuguese. The welcome screen asks which one; to change
it later, open Settings (Configurações) > Language (Idioma) > choose > Save (Salvar). The dashboard, radio
messages, reports and analysis switch right away; close and reopen the app so the English voice
(British "Ryan" by default) and the English microphone start too.

Works with F1 25 on PS5, Xbox or PC. Everything is free. No account needed.


Requirements
------------
- A Windows 10 or 11 PC or laptop on the same network as the console (or the PC running the game).
- Internet connection (the voice uses Microsoft's free online voices; the microphone models are
  downloaded the first time).
- Microsoft Edge (already installed on Windows).


Installation (about 2 minutes)
------------------------------
1. Unzip the folder to C:\Engenheiro (or any folder you like; avoid OneDrive folders).
2. Open "Engenheiro.exe".
   - Windows may show "Windows protected your PC" because the app is not signed:
     click "More info" and then "Run anyway".
   - When Windows Firewall asks, tick "Private networks" and click "Allow".
     (Without this the app cannot receive the data from the console.)
3. The dashboard opens in its own window. Close the window to stop the app; the session is saved.
   The first time, a welcome screen asks for your language and name and shows the IP for the game.
   Tip: right-click the .exe > Send to > Desktop (create shortcut).


Game settings (F1 25 > Settings > Telemetry Settings)
-----------------------------------------------------
   UDP Telemetry: On
   UDP Broadcast Mode: Off
   UDP IP Address: the IP of the PC running the app
                   (playing on the same PC? use 127.0.0.1)
   UDP Port: 20777
   UDP Send Rate: 20Hz
   UDP Format: 2025 (or 2026 with the 2026 Season Pack)
To find your PC's IP: press Windows + R, type cmd, press Enter, type ipconfig and look for
"IPv4 Address" (something like 192.168.0.15).

Then start any session (practice, qualifying, race, time trial). The dashboard shows
"game connected" in green and the engineer says "Radio check. I'm with you."


Demo (without the game)
-----------------------
With the game closed, the "Waiting for the game" screen has demo buttons (race, qualifying, practice):
the app simulates a short session with the real voice and radio, saving nothing. Settings and History
are always available at the top.


Hearing the radio while you race
--------------------------------
- Laptop speakers or any headset connected to the PC, or
- Open the dashboard on your phone (http://PC-IP:8080), tap "Play radio here" and use your
  phone earbuds.


Talking to the engineer (optional)
----------------------------------
Uses the default microphone of the PC. Say "Engineer" followed by the question, for example:
"Engineer, what's the gap to Verstappen?", "has Leclerc pitted?", "will the tyres make it to the end?",
"when do I pit?", "where am I losing time?", "I have understeer on entry", "quiet" / "talk to me".
Or press the "Talk" button on the dashboard, or type the question in the box under the radio.
The first time, the app downloads the English speech models (about 40 MB + 250 MB), so give it a
few minutes with internet. You can also map controller buttons:
F1 25 > Settings > Controls > edit mapping > "UDP Action 1..7":
   1 = situation (position and gaps)   2 = tyres and fuel   3 = strategy
   4 = repeat last message             5 = open the microphone
   6 = radio check ("loud and clear"; the engineer also calls a radio check before every race)
   7 = rival strategy
In the race he also calls retirements (who, where and why), slow or stopped cars, contact, rival
wing damage, drivers losing time, rival pit predictions and undercut/overcut chances. Add your rivals
in Settings > Driver (your teammate is included). A quiet radio beep confirms he heard the wake word.


Using SimHub at the same time
-----------------------------
Only one program can use port 20777. The engineer forwards a copy of the data to port 20778,
so in SimHub set the game UDP port to 20778.


Settings and history
--------------------
In the dashboard: "Settings" (language, voice, microphone, alerts, your name) and
"History" (all recorded sessions with summary, analysis, report and setup used).
Recorded files are in the "sessoes" folder.


Updates
-------
When a new version is out, a green "⬆ v..." button appears at the top of the dashboard. Download the
new zip from the project page and extract it over the same folder: your settings, sessions and
setups are kept.


Troubleshooting
---------------
- "no game data": check the IP and port in the game, allow the app in the
  Firewall (Private networks), and make sure the PC and the console are on the same network.
- Port 20777 already in use: close SimHub (or change SimHub to port 20778, see above).
- No voice: check the internet connection and the PC volume. Without internet the app uses the
  Windows voice as a backup.
- Anything else: open an issue at github.com/yohanfv/engenheiro/issues and attach the file
  engenheiro.log from the app folder.


Credits and license
-------------------
Created by Yohan Vieira. Built with the help of Claude (Anthropic).
Free software under the MIT License (LICENSE.txt). Third-party components and data, including
Pits n' Giggles (MIT) and TracingInsights (Apache 2.0), are listed in THIRD_PARTY_NOTICES.txt.

Unofficial fan project. Not affiliated with, endorsed or sponsored by Formula 1, the FIA, Electronic
Arts or Codemasters. F1 and FORMULA 1 are trademarks of Formula One Licensing B.V.
