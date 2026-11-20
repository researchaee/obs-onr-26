@echo off
rem Recolha diaria do SNIRH (volume e cota das albufeiras) a partir deste PC.
rem Corre pelo Agendador de Tarefas ("ONR - Recolha SNIRH"). O SNIRH bloqueia os servidores do GitHub.
setlocal
cd /d "%~dp0..\.."
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "LOGDIR=%LOCALAPPDATA%\ONR"
set "LOG=%LOGDIR%\recolha_snirh.log"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "PY=python"
py -3 --version >nul 2>&1 && set "PY=py -3"

echo ==== %date% %time% >> "%LOG%"
git pull --rebase --quiet >> "%LOG%" 2>&1
%PY% scripts\onr_clima_recolha.py --so-snirh --registo _Recolhas_SNIRH.csv --orcamento-snirh 30 >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"

git add dados/clima/fClima_Albufeira.csv dados/clima/_Recolhas_SNIRH.csv >> "%LOG%" 2>&1
git diff --cached --quiet
if %ERRORLEVEL%==0 (
  echo Sem alteracoes. >> "%LOG%"
  goto fim
)
git commit --quiet -m "Clima SNIRH: recolha do PC" >> "%LOG%" 2>&1
git pull --rebase --quiet >> "%LOG%" 2>&1
git push --quiet >> "%LOG%" 2>&1
if errorlevel 1 echo ERRO no git push >> "%LOG%"

:fim
echo codigo de saida do recolhedor: %RC% >> "%LOG%"
exit /b %RC%
