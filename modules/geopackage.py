"""Module: geopackage.py

This module contains the functions concerning GeoPackages.
"""

from pathlib import Path

from osgeo import ogr
from qgis.core import (
    Qgis,
    QgsLayerTree,
    QgsMapLayer,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
)
from qgis.gui import QgisInterface

from .general import (
    clear_attribute_table,
    display_summary_message,
    generate_summary_message,
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
    """Add the selected layers to the project's GeoPackage."""

    project: QgsProject = get_current_project()
    gpkg_path: Path = project_gpkg()
    layer = get_selected_layer(plugin)
    new_layer_name: str = f"{layer.name()} - Massenermittlung"

    results: dict = {"successes": 0, "failures": []}

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = new_layer_name
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer

    error = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(gpkg_path), project.transformContext(), options
    )
    if error[0] == QgsVectorFileWriter.WriterError.NoError:
        results["successes"] += 1

        # Load the new layer from the GeoPackage to clear its attributes
        # (the attributes that are imported fom AutoCAD are useless)
        uri: str = f"{gpkg_path}|layername={layer.name()}"
        gpkg_layer = QgsVectorLayer(uri, layer.name(), "ogr")
        if gpkg_layer.isValid():
            clear_attribute_table(gpkg_layer)
        else:
            # This is an unlikely scenario if writing just succeeded,
            # but good to handle.
            plugin.iface.messageBar().pushMessage(
                "Warning",
                (
                    f"Could not reload layer '{layer.name()}' from GeoPackage "
                    "to clear attributes."
                ),
                level=Qgis.Warning,
            )
    else:
        results["failures"].append((layer.name(), error[1]))

    message, level = generate_summary_message(
        successes=results["successes"],
        failures=results["failures"],
        action="Moved",
    )

    display_summary_message(plugin, message, level)


def add_layer_from_gpkg_to_project(plugin: QgisInterface) -> None:
    """Add the new layer from the project's GeoPackage to the project."""
    project: QgsProject = get_current_project()
    selected_layers: list[QgsMapLayer] = get_selected_layer(plugin)
    gpkg_path: Path = project_gpkg()
    gpkg_path_str = str(gpkg_path)

    root: QgsLayerTree | None = project.layerTreeRoot()
    if not root:
        plugin.iface.messageBar().pushMessage(
            "Error", "Could not get layer tree root.", level=Qgis.Critical
        )
        return

    added_layers: list[str] = []
    not_found_layers: list[str] = []

    for layer_to_find in selected_layers:
        layer_name: str = layer_to_find.name()

        # Construct the layer URI and create a QgsVectorLayer
        uri: str = f"{gpkg_path_str}|layername={layer_name}"
        gpkg_layer = QgsVectorLayer(uri, layer_name, "ogr")

        if not gpkg_layer.isValid():
            not_found_layers.append(layer_name)
            continue

        # Add the layer to the project registry first, but not the layer tree
        project.addMapLayer(gpkg_layer, addToLegend=False)
        # Then, insert it at the top of the layer tree
        root.insertLayer(0, gpkg_layer)
        added_layers.append(layer_name)

    if added_layers:
        plural_s: str = "s" if len(added_layers) > 1 else ""
        plugin.iface.messageBar().pushMessage(
            "Success",
            f"Added {len(added_layers)} layer{plural_s} from the GeoPackage.",
            level=Qgis.Success,
        )
    if not_found_layers:
        count: int = len(not_found_layers)
        plural_s = "s" if count > 1 else ""
        layer_list: str = ", ".join(not_found_layers)
        plugin.iface.messageBar().pushMessage(
            "Warning",
            f"Could not find {count} layer{plural_s} in GeoPackage: {layer_list}",
            level=Qgis.Warning,
        )
