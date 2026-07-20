@echo off
REM Construieste executabilul Windows standalone (nu necesita Python instalat
REM pe calculatorul pe care va rula aplicatia).
setlocal

echo Instalare dependente de build...
pip install -r requirements-build.txt
if errorlevel 1 goto :error

echo.
echo Construire executabil (PyInstaller)...
python -m PyInstaller --noconfirm KenoLib.spec
if errorlevel 1 goto :error

if exist ml_model.joblib (
    echo.
    echo Copiere model ML pre-antrenat langa executabil...
    copy /Y ml_model.joblib dist\KenoLib\ml_model.joblib >nul
)

echo.
echo ============================================================
echo  Gata! Aplicatia executabila se afla in:
echo    dist\KenoLib\KenoLib.exe
echo.
echo  Pentru a o folosi pe alt calculator, copiaza intregul folder
echo    dist\KenoLib
echo  (nu doar fisierul .exe) si ruleaza KenoLib.exe din el.
echo ============================================================
pause
exit /b 0

:error
echo.
echo A aparut o eroare la construirea executabilului.
pause
exit /b 1
