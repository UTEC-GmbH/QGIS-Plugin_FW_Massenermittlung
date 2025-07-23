
Notes:

  * Create a symbolic link

    Open Command Prompt as an Administrator.
    Create the symbolic link using the "mklink /D" command. 
    The format is: mklink /D <Link_Path> <Target_Path>
    mklink /D "C:\Users\**USER_NAME**\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\**PLUGIN_NAME**" "C:\**DEV_DIRECTORY**\**PLUGIN_NAME**"


  * Compile the resources file using pyrcc5

	  use "compile.bat"


  * Run the tests (``make test``)


  * You can use the Makefile to compile your Ui and resource files when
    you make changes. This requires GNU make (gmake)


For more information, see the PyQGIS Developer Cookbook at:
http://www.qgis.org/pyqgis-cookbook/index.html




