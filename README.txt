Plugin Builder Results

Your plugin MoveLayersToGPKG was created in:
    C:/Users/fl/Documents/Python/QGIS Plugins\move_layers_to_gpkg

Your QGIS plugin directory is located at:
    C:/Users/fl/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins

What's Next:

  * Copy the entire directory containing your new plugin to the QGIS Plugin Directory 
  -> or create a symbolic link (see below ++)

  * Compile the resources file using pyrcc5
	→ use the OSGeo4W Shell that was installed with QGIS
	→ cd c:\Users\fl\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\QGIS_plugin_move_layers_to_gpkg
	→ pyrcc5 -o resources.py resources.qrc

  * Run the tests (``make test``)

  * Test the plugin by enabling it in the QGIS plugin manager

  * Customize it by editing the implementation file: ``move_layers_to_gpkg.py``

  * Create your own custom icon, replacing the default icon.png

  * Modify your user interface by opening MoveLayersToGPKG_dialog_base.ui in Qt Designer

  * You can use the Makefile to compile your Ui and resource files when
    you make changes. This requires GNU make (gmake)

For more information, see the PyQGIS Developer Cookbook at:
http://www.qgis.org/pyqgis-cookbook/index.html

(C) 2011-2018 GeoApt LLC - geoapt.com


++
How to set up a Symbolic Link on Windows:

Open Command Prompt as an Administrator.

Create the symbolic link using the mklink /D command. The format is mklink /D <Link_Path> <Target_Path>.

mklink /D "C:\Users\**user name**\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\**Plugin name**" "C:\dev\**Plugin name**"

Now, Windows treats the link in the plugins directory as if it were the actual folder from your C:\dev\ directory. You can edit your code in C:\dev\, and QGIS will see the changes instantly, ready for you to use Plugin Reloader.