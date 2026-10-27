@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set "RAIZ=%CD%"
title Gerando o Engenheiro
echo ================================================================
echo   Gerando o programa "Engenheiro.exe" a partir do codigo
echo   Leva uns 10 minutos na primeira vez. Precisa de internet.
echo ================================================================
echo.

echo [1/4] Preparando o Python 3.12 so para gerar o programa...
py install 3.12 >nul 2>&1
set "PYB="
py -V:3.12 --version >nul 2>&1 && set "PYB=py -V:3.12"
if not defined PYB py -3.12 --version >nul 2>&1 && set "PYB=py -3.12"
if not defined PYB (
  echo     Nao achei o Python 3.12; vou tentar com o Python que voce ja tem.
  set "PYB=py"
)
if not exist ".construcao\Scripts\python.exe" %PYB% -m venv .construcao || goto erro
set "VPY=.construcao\Scripts\python.exe"

echo [2/4] Instalando as bibliotecas (voz, microfone, Whisper)...
"%VPY%" -m pip install --upgrade pip >nul
"%VPY%" -m pip install -r requirements.txt pyinstaller || goto erro

echo [3/4] Montando o programa...
"%VPY%" scripts\construir.py --nesta-pasta || goto erro
rem versoes antigas tinham "F1" no nome: apaga o programa e o atalho antigos
if exist "Engenheiro F1.exe" del /q "Engenheiro F1.exe" >nul 2>&1
powershell -NoProfile -Command "Remove-Item -ErrorAction SilentlyContinue ([Environment]::GetFolderPath('Desktop')+'\Engenheiro F1.lnk')" >nul 2>&1

echo [4/4] Criando o atalho na area de trabalho...
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Engenheiro.lnk'); $s.TargetPath='%RAIZ%\Engenheiro.exe'; $s.WorkingDirectory='%RAIZ%'; $s.IconLocation='%RAIZ%\icone.ico'; $s.Save()" >nul 2>&1

echo.
echo ================================================================
echo   Pronto! Abra pelo atalho "Engenheiro" na area de trabalho
echo   (ou pelo "Engenheiro.exe" na pasta do projeto).
echo   A pasta .construcao pode ser apagada se quiser liberar espaco.
echo ================================================================
pause
exit /b 0

:erro
echo.
echo [ERRO] Algo deu errado. Tire um print desta janela e abra uma issue no GitHub.
pause
exit /b 1
