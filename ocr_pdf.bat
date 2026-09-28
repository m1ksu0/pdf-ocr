@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=C:\Apps\Python\python.exe"
if not exist "%PY%" set "PY=python"

set "PDF=%~1"
if "%PDF%"=="" set /p PDF=Vedä PDF tähän ikkunaan tai kirjoita polku, ja paina Enter:
set "PDF=%PDF:"=%"

set "DPI=400"
set /p DPI=Tarkkuus dpi (Enter = 400, isompi = tarkempi mutta hitaampi, esim. 600):
if "%DPI%"=="" set "DPI=400"

set "PSM=3"
set /p PSM=Sivunjakotila psm (Enter = 3 automaattinen, 6 = taulukot/lomakkeet, 4 = yksi sarake):
if "%PSM%"=="" set "PSM=3"

"%PY%" ocr_pdf.py "%PDF%" --dpi %DPI% --psm %PSM%

echo.
pause
