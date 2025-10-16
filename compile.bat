@echo off

:: This script compiles resources and translation files.
:: It assumes you have the QGIS environment (and thus pyrcc5, pylupdate5, lrelease) in your PATH.
:: Run this from the OSGeo4W Shell.

echo Compiling resource file (resources.qrc)...
pyrcc5 -o "resources.py" "resources.qrc"

echo.
echo Creating/updating translation source file (i18n/de.ts)...
if not exist i18n mkdir i18n
setlocal enabledelayedexpansion
set "PY_FILES="
for /f "delims=" %%i in ('dir /b /s *.py ^| findstr /v /i "__pycache__"') do (
    set "PY_FILES=!PY_FILES! %%i"
)
pylupdate5 -noobsolete -verbose !PY_FILES! -ts i18n/de.ts
endlocal

echo.
echo Compiling translation file (i18n/de.qm)...
lrelease i18n/de.ts

echo.
echo Compilation finished.