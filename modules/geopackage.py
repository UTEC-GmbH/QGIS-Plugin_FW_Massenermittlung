"""Module: geopackage.py

This module contains the functions concerning GeoPackages.
"""

from pathlib import Path

from osgeo import ogr
from qgis.core import (
    Qgis,
    QgsLayerTree,
    QgsMessageLog,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.gui import QgisInterface

from .general import (
    fix_layer_name,
    get_current_project,
    get_selected_layer,
    raise_runtime_error,
)


def project_gpkg() -> Path:
    """Check if a GeoPackage with the same name as the project
    exists in the project folder and creates it if not.

    Example: for a project 'my_project.qgz',
    it looks for 'my_project.gpkg' in the same directory.

    :returns: The Path object to the GeoPackage.
    :raises RuntimeError: If the project is not saved.
    :raises IOError: If the GeoPackage file cannot be created.
    """
    project: QgsProject = get_current_project()
    project_path_str: str = project.fileName()
    if not project_path_str:
        raise_runtime_error("Project is not saved. Please save the project first.")

    project_path: Path = Path(project_path_str)
    gpkg_path: Path = project_path.with_suffix(".gpkg")

    if not gpkg_path.exists():
        driver = ogr.GetDriverByName("GPKG")
        data_source = driver.CreateDataSource(str(gpkg_path))
        if data_source is None:
            raise_runtime_error(f"Failed to create GeoPackage at: {gpkg_path}")

        # Dereference the data source to close the file and release the lock.
        data_source = None

    return gpkg_path


def create_empty_layer_in_gpkg(plugin: QgisInterface) -> None:
    """Create an empty point layer in the project's GeoPackage."""

    project: QgsProject = get_current_project()
    gpkg_path: Path = project_gpkg()
    new_layer_name: str = (
        f"{fix_layer_name(get_selected_layer(plugin).name())} - Massenermittlung"
    )
    empty_layer = QgsVectorLayer(
        f"Point?crs={project.crs().authid()}", "in_memory_layer", "memory"
    )

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = new_layer_name
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer

    error: tuple = QgsVectorFileWriter.writeAsVectorFormatV3(
        empty_layer, str(gpkg_path), project.transformContext(), options
    )
    if error[0] == QgsVectorFileWriter.WriterError.NoError:
        QgsMessageLog.logMessage(
            f"Empty layer created: {new_layer_name}", "Success", level=Qgis.Success
        )
    else:
        raise_runtime_error(
            f"Failed to create empty layer '{new_layer_name}' - Error: {error[1]}"
        )


def add_layer_from_gpkg_to_project(plugin: QgisInterface) -> None:
    """Add the new layer from the project's GeoPackage to the project."""
    project: QgsProject = get_current_project()
    gpkg_path: Path = project_gpkg()
    gpkg_path_str = str(gpkg_path)
    new_layer_name: str = (
        f"{fix_layer_name(get_selected_layer(plugin).name())} - Massenermittlung"
    )

    root: QgsLayerTree | None = project.layerTreeRoot()
    if not root:
        raise_runtime_error("Could not get layer tree root.")

    # Construct the layer URI and create a QgsVectorLayer
    uri: str = f"{gpkg_path_str}|layername={new_layer_name}"
    gpkg_layer = QgsVectorLayer(uri, new_layer_name, "ogr")

    if not gpkg_layer.isValid():
        raise_runtime_error("could not find layer in GeoPackage")

    # Add the layer to the project registry first, but not the layer tree
    project.addMapLayer(gpkg_layer, addToLegend=False)
    # Then, insert it at the top of the layer tree
    root.insertLayer(0, gpkg_layer)

    QgsMessageLog.logMessage(
        f"Added {new_layer_name} from the GeoPackage to the project.",
        "Success",
        level=Qgis.Success,
    )
