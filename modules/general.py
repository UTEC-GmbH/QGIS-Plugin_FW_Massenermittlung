"""Module: general.py

This module contains general functions.
"""

import contextlib
import re
from pathlib import Path
from typing import NoReturn

from osgeo import ogr
from qgis.core import (
    Qgis,
    QgsLayerTree,
    QgsLayerTreeNode,
    QgsMapLayer,
    QgsMessageLog,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgisInterface, QgsLayerTreeView


def raise_runtime_error(error_msg: str) -> NoReturn:
    """Log a critical error and raise a RuntimeError.

    This helper function standardizes error handling by ensuring that a critical
    error is raised as a Python exception to halt the current operation.

    :param error_msg: The error message to display and include in the exception.
    :raises RuntimeError: Always raises a RuntimeError with the provided error message.
    """
    QgsMessageLog.logMessage(error_msg, "Error", level=Qgis.Critical)
    raise RuntimeError(error_msg)


def get_current_project() -> QgsProject:
    """Check if a QGIS project is currently open and returns the project instance.

    If no project is open, an error message is logged.

    Returns:
    QgsProject: The current QGIS project instance.
    """
    project: QgsProject | None = QgsProject.instance()
    if project is None:
        raise_runtime_error("No QGIS project is currently open.")

    return project


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


class LayerManager:
    """A class to manage the layers used in the plugin."""

    def __init__(self, plugin: QgisInterface | None = None) -> None:
        """Initialize the layer manager class."""
        self._selected_layer: QgsVectorLayer | None = None
        self._new_layer: QgsVectorLayer | None = None
        self._plugin: QgisInterface | None = plugin

    def fix_layer_name(self, name: str) -> str:
        """Fix encoding mojibake and sanitize a string to be a valid layer name.

        This function first attempts to fix a common mojibake encoding issue,
        where a UTF-8 string was incorrectly decoded as cp1252
        (for example: 'Ãœ' becomes 'Ü').
        It then sanitizes the string to remove or replace characters
        that might be problematic in layer names,
        especially for file-based formats or databases.

        :param name: The potentially garbled and raw layer name.
        :returns: A fixed and sanitized version of the name.
        """
        fixed_name: str = name
        with contextlib.suppress(UnicodeEncodeError):
            fixed_name = name.encode("cp1252").decode("utf-8")

        # Remove or replace problematic characters
        sanitized_name: str = re.sub(r'[<>:"/\\|?*,]+', "_", fixed_name)

        return sanitized_name

    def get_selected_layer(self) -> QgsMapLayer:
        """Collect the selected layer in the QGIS layer tree view.

        :returns: The selected QgsMapLayer object.
        """
        if self._plugin is None:
            raise_runtime_error("Plugin is not set.")
        layer_tree: QgsLayerTreeView | None = self._plugin.layerTreeView()
        if not layer_tree:
            raise_runtime_error("Could not get layer tree view.")

        selected_nodes: list[QgsLayerTreeNode] = layer_tree.selectedNodes()
        if len(selected_nodes) > 1:
            raise_runtime_error("Multiple layers selected.")
        if not selected_nodes:
            raise_runtime_error("No layer selected.")

        selected_node: QgsLayerTreeNode = next(iter(selected_nodes))
        if not isinstance(selected_node, QgsLayerTreeNode) and selected_node.layer():
            raise_runtime_error("No layer selected.")

        selected_layer = selected_node.layer()
        if not isinstance(selected_layer, QgsMapLayer):
            raise_runtime_error("No layer selected.")

        if (
            selected_layer.type() != QgsMapLayer.VectorLayer
            and selected_layer.geometryType() != QgsWkbTypes.LineGeometry
        ):
            raise_runtime_error("The selected layer is not a line layer.")

        return selected_node.layer()

    def initialize_selected_layer(self) -> None:
        """Initialize the selected layer."""
        if self._plugin is None:
            raise_runtime_error("Plugin is not set.")
        self._selected_layer = self.get_selected_layer()

    def create_new_layer(self) -> None:
        """Create an empty point layer in the project's GeoPackage."""

        project: QgsProject = get_current_project()
        gpkg_path: Path = project_gpkg()
        new_layer_name: str = (
            f"{self.fix_layer_name(self.selected_layer.name())} - Massenermittlung"
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

        root: QgsLayerTree | None = project.layerTreeRoot()
        if not root:
            raise_runtime_error("Could not get layer tree root.")

        # Construct the layer URI and create a QgsVectorLayer
        uri: str = f"{gpkg_path!s}|layername={new_layer_name}"
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
        self.new_layer = gpkg_layer

    def initialize_new_layer(self) -> None:
        """Initialize the selected layer."""
        if self._plugin is None:
            raise_runtime_error("Plugin is not set.")
        self._selected_layer = self.create_new_layer()

    @property
    def selected_layer(self) -> QgsVectorLayer:
        """The selected layer in the plugin."""
        if self._selected_layer is None:
            self.initialize_selected_layer()
        if self._selected_layer is None:
            raise_runtime_error("Selected layer is not set.")
        return self._selected_layer

    @selected_layer.setter
    def selected_layer(self, layer: QgsVectorLayer) -> None:
        self._selected_layer = layer

    @property
    def new_layer(self) -> QgsVectorLayer:
        """The new layer created by the plugin."""
        if self._new_layer is None:
            self.initialize_new_layer()
        if self._new_layer is None:
            raise_runtime_error("New layer is not set.")
        return self._new_layer

    @new_layer.setter
    def new_layer(self, layer: QgsVectorLayer) -> None:
        self._new_layer = layer
