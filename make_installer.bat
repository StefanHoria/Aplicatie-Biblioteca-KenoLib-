@echo off
REM ============================================================================
REM  KenoLib - construieste installerul complet dintr-o singura comanda.
REM
REM  Ce face:
REM    1) construieste executabilul standalone (PyInstaller) -- include Python
REM       si toate bibliotecile, deci pe calculatorul-tinta nu trebuie nimic;
REM    2) se asigura ca Inno Setup e prezent (il descarca si instaleaza automat
REM       daca lipseste) -- necesar DOAR pe acest calculator, cel pe care
REM       construiesti installerul;
REM    3) compileaza installerul intr-un singur fisier:
REM         installer\Output\KenoLib-Setup.exe
REM
REM  Acel fisier este tot ce trebuie copiat pe alt laptop: se ruleaza si
REM  instaleaza aplicatia, cu scurtaturi si dezinstalare, fara Python.
REM ============================================================================
setlocal enableextensions
cd /d "%~dp0"

echo ============================================================
echo   KenoLib - construire installer (KenoLib-Setup.exe)
echo ============================================================
echo.

REM --- 1) Dependinte de build + executabil standalone --------------------------
echo [1/3] Instalare dependinte de build...
python -m pip install -r requirements-build.txt
if errorlevel 1 goto :error

echo.
echo [1/3] Construire executabil (PyInstaller)...
python -m PyInstaller --noconfirm KenoLib.spec
if errorlevel 1 goto :error

if not exist "dist\KenoLib\KenoLib.exe" (
    echo     Executabilul nu a fost creat -- opresc.
    goto :error
)

REM --- 2) Asigura Inno Setup (ISCC.exe) ---------------------------------------
echo.
echo [2/3] Verificare Inno Setup...
call :find_iscc
if defined ISCC goto :have_iscc

echo     Inno Setup nu este instalat pe acest calculator.
echo     Se descarca si se instaleaza automat (necesita internet)...
REM  Link direct si permanent catre binarul oficial (release GitHub semnat de
REM  jrsoftware). NU folosi jrsoftware.org/download.php/is.exe -- acela intoarce
REM  o pagina HTML, nu executabilul.
set "ISURL=https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri '%ISURL%' -OutFile \"$env:TEMP\innosetup-setup.exe\" -UseBasicParsing } catch { exit 1 }"
if errorlevel 1 goto :error_inno
if not exist "%TEMP%\innosetup-setup.exe" goto :error_inno

echo     Instalare Inno Setup (poate aparea o intrebare de administrator)...
"%TEMP%\innosetup-setup.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-
if errorlevel 1 goto :error_inno

call :find_iscc
if not defined ISCC goto :error_inno

:have_iscc
echo     Inno Setup: "%ISCC%"

REM --- 3) Compileaza installerul ----------------------------------------------
echo.
echo [3/3] Construire installer...
"%ISCC%" "installer\KenoLib.iss"
if errorlevel 1 goto :error

echo.
echo ============================================================
echo   GATA! Installerul se afla in:
echo      installer\Output\KenoLib-Setup.exe
echo.
echo   Copiaza acest SINGUR fisier pe orice laptop cu Windows si
echo   ruleaza-l. Instaleaza tot ce e nevoie (Python este inclus
echo   in aplicatie) -- nu trebuie instalat nimic altceva.
echo ============================================================
pause
exit /b 0


REM ---------------------------------------------------------------------------
REM  Subrutina: cauta ISCC.exe (compilatorul Inno Setup) in PATH si in locurile
REM  uzuale de instalare. Rezultatul e pus in variabila ISCC (gol daca lipseste).
REM  Foloseste if-uri pe o singura linie ca sa evite problema parantezei din
REM  "Program Files (x86)" in blocurile ( ).
REM ---------------------------------------------------------------------------
:find_iscc
set "ISCC="
for %%P in (ISCC.exe) do if not defined ISCC if not "%%~$PATH:P"=="" set "ISCC=%%~$PATH:P"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
goto :eof


:error_inno
echo.
echo Instalarea automata a Inno Setup a esuat.
echo Verifica internetul sau instaleaza-l manual de la:
echo    https://jrsoftware.org/isdl.php
echo apoi ruleaza din nou acest script.
pause
exit /b 1

:error
echo.
echo A aparut o eroare. Vezi mesajele de mai sus.
pause
exit /b 1
