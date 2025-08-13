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
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsLayerTree,
    QgsLayerTreeNode,
    QgsMessageLog,
    QgsProject,
    QgsVectorDataProvider,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgisInterface, QgsLayerTreeView

from . import constants as cont


def log_debug(message: str, msg_level: Qgis.MessageLevel = Qgis.Info) -> None:
    """Log a debug message.

    :param message: The message to log.
    """
    QgsMessageLog.logMessage(message, "Massenermittlung", level=msg_level)


def log_summary(item_name: str, checked_count: int, found_count: int) -> None:
    """Log a summary message for a feature finding operation."""
    if found_count:
        log_debug(
            f"{item_name}: {checked_count} Linien geprüft → "
            f"{found_count} {item_name} gefunden.",
            Qgis.Success,
        )
    else:
        log_debug(
            f"{item_name}: {checked_count} Linien geprüft, "
            f"aber keine {item_name} gefunden!",
            Qgis.Warning,
        )


def raise_runtime_error(error_msg: str) -> NoReturn:
    """Log a critical error and raise a RuntimeError.

    This helper function standardizes error handling by ensuring that a critical
    error is raised as a Python exception to halt the current operation.

    :param error_msg: The error message to display and include in the exception.
    :raises RuntimeError: Always raises a RuntimeError with the provided error message.
    """
    QgsMessageLog.logMessage(error_msg, "Error", level=Qgis.Critical)
    raise RuntimeError(error_msg)


class UserError(Exception):
    """Custom exception for user-related errors in the plugin."""


def raise_user_error(error_msg: str, plugin: QgisInterface | None = None) -> NoReturn:
    """Log a warning message and raise a UserError.

    This helper function standardizes error handling by ensuring that a warning
    is raised to halt the current operation because of a user error.

    :param error_msg: The error message to display and include in the exception.
    :raises UserError: Always raises a UserError with the provided error message.
    """
    if plugin and (msg_bar := plugin.messageBar()):
        msg_bar.pushMessage("Error", error_msg, level=Qgis.Critical)

    QgsMessageLog.logMessage(error_msg, "Error", level=Qgis.Critical)
    raise UserError(error_msg)


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
        self._project: QgsProject | None = None
        self._plugin: QgisInterface | None = plugin
        self._selected_layer: QgsVectorLayer | None = None
        self._new_layer: QgsVectorLayer | None = None

    @property
    def project(self) -> QgsProject:
        """The current QGIS project."""
        if self._project is None:
            self._project = get_current_project()
        return self._project

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

    def initialize_selected_layer(self) -> None:
        """Initialize the selected layer."""
        if self._plugin is None:
            raise_runtime_error("Plugin is not set.")
        self._selected_layer = self.get_selected_layer()

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

    def initialize_new_layer(self) -> None:
        """Initialize the new layer."""
        if self._plugin is None:
            raise_runtime_error("Plugin is not set.")
        self.new_layer = self.create_new_layer()

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
        with contextlib.suppress(UnicodeEncodeError, UnicodeDecodeError):
            fixed_name = name.encode("cp1252").decode("utf-8")

        # Remove or replace problematic characters
        sanitized_name: str = re.sub(r'[<>:"/\\|?*,]+', "_", fixed_name)

        return sanitized_name

    def reproject_layer_to_project_crs(self, layer: QgsVectorLayer) -> QgsVectorLayer:
        """Reprojects a vector layer to the project's CRS.

        Creates a new in-memory layer with the same fields and reprojects
        all features from the source layer into it.

        :param layer: The source QgsVectorLayer to reproject.
        :returns: A new, reprojected in-memory QgsVectorLayer.
        """

        # If the layer's CRS is already the same as the project's CRS, return a clone.
        if layer.crs() == self.project.crs():
            return layer.clone()

        # Create a new in-memory layer with the target CRS
        geometry_type_str: str = QgsWkbTypes.displayString(layer.wkbType())
        reprojected_layer = QgsVectorLayer(
            f"{geometry_type_str}?crs={self.project.crs().authid()}",
            layer.name(),
            "memory",
        )

        # Copy fields from the source layer
        data_provider: QgsVectorDataProvider | None = reprojected_layer.dataProvider()
        if data_provider is None:
            raise_runtime_error(
                f"Could not get data provider for layer: {reprojected_layer.name()}"
            )

        data_provider.addAttributes(layer.fields())
        reprojected_layer.updateFields()

        # Prepare coordinate transformation
        transform = QgsCoordinateTransform(
            layer.crs(), self.project.crs(), self.project.transformContext()
        )

        # Copy and reproject features
        old_features: list[QgsFeature] = list(layer.getFeatures())
        if not old_features:
            return reprojected_layer

        new_features: list[QgsFeature] = []
        for feature in old_features:
            new_feature = QgsFeature()
            new_feature.setFields(reprojected_layer.fields(), initAttributes=True)
            new_feature.setAttributes(feature.attributes())

            geom = feature.geometry()
            if geom.transform(transform) != 0:  # 0 means success
                log_debug(
                    f"Feature {feature.id()} could not be reprojected.", Qgis.Warning
                )
                continue

            new_feature.setGeometry(geom)
            new_features.append(new_feature)

        data_provider.addFeatures(new_features)
        reprojected_layer.updateExtents()

        return reprojected_layer

    def get_selected_layer(self) -> QgsVectorLayer:
        """Collect the selected layer in the QGIS layer tree view and reprojects it.

        :returns: The selected and reprojected QgsVectorLayer object.
        :raises RuntimeError: If no layer is selected, multiple layers are selected,
                              or the selected layer is not a line vector layer.
        """
        if self._plugin is None:
            raise_runtime_error("Plugin is not set.")
        layer_tree: QgsLayerTreeView | None = self._plugin.layerTreeView()
        if not layer_tree:
            raise_runtime_error("Could not get layer tree view.")

        selected_nodes: list[QgsLayerTreeNode] = layer_tree.selectedNodes()
        if len(selected_nodes) > 1:
            raise_user_error("Multiple layers selected.", self._plugin)
        if not selected_nodes:
            raise_user_error("No layer selected.", self._plugin)

        selected_node: QgsLayerTreeNode = next(iter(selected_nodes))
        if not selected_node.layer():
            raise_user_error("Selected node is not a layer.", self._plugin)

        selected_layer = selected_node.layer()
        if not isinstance(selected_layer, QgsVectorLayer):
            raise_user_error("Selected layer is not a vector layer.", self._plugin)

        if selected_layer.geometryType() != QgsWkbTypes.LineGeometry:
            raise_user_error("The selected layer is not a line layer.", self._plugin)

        # Reproject the layer to the project's CRS
        return self.reproject_layer_to_project_crs(selected_layer)

    def create_new_layer(self) -> QgsVectorLayer:
        """Create an empty point layer in the project's GeoPackage."""

        gpkg_path: Path = project_gpkg()
        new_layer_name: str = (
            f"{self.fix_layer_name(self.selected_layer.name())}"
            f"{cont.Names.new_layer_suffix}"
        )

        if existing_layers := self.project.mapLayersByName(new_layer_name):
            self.project.removeMapLayers([layer.id() for layer in existing_layers])

        empty_layer = QgsVectorLayer(
            f"Point?crs={self.project.crs().authid()}", "in_memory_layer", "memory"
        )

        data_provider: QgsVectorDataProvider | None = empty_layer.dataProvider()
        if data_provider is None:
            raise_runtime_error(
                f"Could not get data provider for layer: {empty_layer.name()}"
            )

        data_provider.addAttributes(
            [QgsField(field.name, field.data_type) for field in cont.NewLayerFields()]
        )
        empty_layer.updateFields()

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = new_layer_name
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer

        error: tuple = QgsVectorFileWriter.writeAsVectorFormatV3(
            empty_layer, str(gpkg_path), self.project.transformContext(), options
        )
        if error[0] == QgsVectorFileWriter.WriterError.NoError:
            log_debug(f"Empty layer created: {new_layer_name}", Qgis.Success)
        else:
            raise_runtime_error(
                f"Failed to create empty layer '{new_layer_name}' - Error: {error[1]}"
            )

        root: QgsLayerTree | None = self.project.layerTreeRoot()
        if not root:
            raise_runtime_error("Could not get layer tree root.")

        # Construct the layer URI and create a QgsVectorLayer
        uri: str = f"{gpkg_path!s}|layername={new_layer_name}"
        gpkg_layer = QgsVectorLayer(uri, new_layer_name, "ogr")

        if not gpkg_layer.isValid():
            raise_runtime_error(
                f"Could not find layer '{new_layer_name}' in GeoPackage '{gpkg_path}'"
            )

        # Add the layer to the project registry first, but not the layer tree
        self.project.addMapLayer(gpkg_layer, addToLegend=False)
        # Then, insert it at the top of the layer tree
        root.insertLayer(0, gpkg_layer)

        log_debug(
            f"Added {new_layer_name} from the GeoPackage to the project.",
            Qgis.Success,
        )

        self.set_layer_style(gpkg_layer)

        return gpkg_layer

    def set_layer_style(self, layer: QgsVectorLayer) -> None:
        """Set the layer style from a QML file."""
        qml_resource_path = (
            ":/compiled_resources/layer_style/massenermittlung_style.qml"
        )
        layer.loadNamedStyle(qml_resource_path)
        layer.triggerRepaint()
