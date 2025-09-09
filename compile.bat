@echo off

:: This script compiles resources and translation files.
:: It assumes you have the QGIS environment (and thus pyrcc5, pylupdate5, lrelease) in your PATH.
:: Run this from the OSGeo4W Shell.

echo Compiling resource file (resources.qrc)...
pyrcc5 -o "resources.py" "resources.qrc"

echo.
echo Creating/updating translation source file (i18n/de.ts)...
if not exist i18n mkdir i18n
pylupdate5 -noobsolete -verbose massenermittlung.py modules/constants.py modules/find_stuff.py modules/general.py -ts i18n/de.ts

echo.
echo Compiling translation file (i18n/de.qm)...
echo NOTE: This will only work if you have already translated i18n/de.ts using Qt Linguist.
lrelease i18n/de.ts

echo.
echo Compilation finished.