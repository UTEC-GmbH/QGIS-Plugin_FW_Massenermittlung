@echo off

:: This script compiles the .qrc file into a Python module.
:: It assumes you have the QGIS environment (and thus pyuic5/pyrcc5) in your PATH.


echo Compiling resource files...
pyrcc5 -o "resources.py" "resources.qrc"

echo Compilation finished.