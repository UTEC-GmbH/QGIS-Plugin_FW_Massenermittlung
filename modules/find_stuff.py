"""Module: find_stuff.py

This module contains the functions that find thnigs in the selected layer.
"""

from qgis.core import (
    Qgis,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsMessageLog,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsSpatialIndex,
    QgsVectorLayer,
)

from .general import LayerManager, get_current_project

SEARCH_RADIUS: float = 0.0000005
CURRENT_PROJECT: QgsProject = get_current_project()


def find_unconnected_endpoints(layer_manager: LayerManager) -> None:
    """Find the endpoints of lines that are not connected to other lines."""
    features_checked: int = 0
    new_points: int = 0
    selected_layer: QgsVectorLayer = layer_manager.selected_layer
    new_layer: QgsVectorLayer = layer_manager.new_layer

    # Set up coordinate transformation
    transform = QgsCoordinateTransform(
        selected_layer.crs(), new_layer.crs(), CURRENT_PROJECT
    )

    # Create a spatial index for the selected layer
    index = QgsSpatialIndex(selected_layer.getFeatures())

    # Start editing the new layer
    new_layer.startEditing()

    for feature in selected_layer.getFeatures():
        features_checked += 1
        geom: QgsGeometry = feature.geometry()
        lines = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
        for line in lines:
            start_point: QgsPointXY = line[0]
            end_point: QgsPointXY = line[-1]

            for point in [start_point, end_point]:
                # Create a small buffer around the point to search for other lines
                search_rect: QgsRectangle = (
                    QgsGeometry.fromPointXY(point)
                    .buffer(SEARCH_RADIUS, 5)
                    .boundingBox()
                )
                intersecting_ids: list[int] = index.intersects(search_rect)

                # If only one line is found, then the endpoint is unconnected
                if len(intersecting_ids) == 1:
                    new_feature = QgsFeature(new_layer.fields())
                    new_feature.setGeometry(
                        QgsGeometry.fromPointXY(transform.transform(point))
                    )
                    if new_layer.addFeature(new_feature):
                        new_points += 1

    if new_points:
        QgsMessageLog.logMessage(
            f"{features_checked} lines checked. "
            f"{new_points} unconnected endpoints found.",
            "Success",
            level=Qgis.Success,
        )
    else:
        QgsMessageLog.logMessage(
            f"{features_checked} lines checked. No unconnected endpoints found.",
            "Warning",
            level=Qgis.Warning,
        )

    # Commit the changes to the new layer
    new_layer.commitChanges()
