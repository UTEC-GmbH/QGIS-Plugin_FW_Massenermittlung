@echo off

:: This script compiles the .qrc file into a Python module.
:: It assumes you have the QGIS environment (and thus pyuic5/pyrcc5) in your PATH.

:: use OSGeo4W Shell (search for OSGeo4W Shell in your start menu)
:: in the shell, navigate to the directory containing this script (using 'cd <directory_path>')
:: and run this script by typing `compile.bat`


echo Compiling resource files...
pyrcc5 -o "resources.py" "resources.qrc"

echo Compilation finished.