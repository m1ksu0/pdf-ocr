@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=C:\Apps\Python\python.exe"
if not exist "%PY%" set "PY=python"

set "PDF=%~1"
if "%PDF%"=="" set /p PDF=Vedä PDF tähän ikkunaan tai kirjoita polku, ja paina Enter:
set "PDF=%PDF:"=%"

echo.
echo Valitse OCR-moottori:
echo   1 = Tesseract (oletus; nopea, tunnistaa a/o-merkit)
echo   2 = RapidOCR (hitaampi; lukee usein lomakkeiden numerot paremmin, ei a/o-merkkeja)
echo   3 = moondream (Ollama, paikallinen nako-kielimalli; nopein VLM-vaihtoehto)
echo   4 = qwen2.5vl (Ollama, paikallinen nako-kielimalli; tarkempi, hitaampi)
set "ENGN=1"
set /p ENGN=Valinta (Enter = 1):
set "ENG=tesseract"
if "%ENGN%"=="2" set "ENG=rapidocr"
if "%ENGN%"=="3" set "ENG=moondream"
if "%ENGN%"=="4" set "ENG=qwen2.5vl"

set "DPI=400"
set /p DPI=Tarkkuus dpi (Enter = 400, isompi = tarkempi mutta hitaampi, esim. 600):
if "%DPI%"=="" set "DPI=400"

set "PSM=3"
set /p PSM=Sivunjakotila psm (Enter = 3 automaattinen, 6 = taulukot/lomakkeet, 4 = yksi sarake):
if "%PSM%"=="" set "PSM=3"

"%PY%" ocr_pdf.py "%PDF%" --engine %ENG% --dpi %DPI% --psm %PSM%

echo.
pause
