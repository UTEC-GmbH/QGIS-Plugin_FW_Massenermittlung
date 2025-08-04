"""Module: find_stuff.py

This module contains the functions that find thnigs in the selected layer.
"""

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsMessageLog,
    QgsPointXY,
    QgsSpatialIndex,
    QgsVectorLayer,
)

from .general import LayerManager


def find_unconnected_endpoints(layer_manager: LayerManager) -> None:
    """Find the endpoints of lines that are not connected to other lines."""
    new_points: list[QgsPointXY] = []
    selected_layer: QgsVectorLayer = layer_manager.selected_layer
    new_layer: QgsVectorLayer = layer_manager.new_layer

    # Create a spatial index for the selected layer
    index = QgsSpatialIndex(selected_layer.getFeatures())

    # Start editing the new layer
    new_layer.startEditing()

    for feature in selected_layer.getFeatures():
        geom: QgsGeometry = feature.geometry()
        lines = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
        for line in lines:
            start_point: QgsPointXY = line[0]
            end_point: QgsPointXY = line[-1]

            for point in [start_point, end_point]:
                # Create a small buffer around the point to search for other lines
                search_rect = (
                    QgsGeometry.fromPointXY(point).buffer(0.5, 5).boundingBox()
                )
                intersecting_ids = index.intersects(search_rect)

                # If only one line is found, then the endpoint is unconnected
                if len(intersecting_ids) == 1:
                    new_feature = QgsFeature()
                    new_feature.setGeometry(QgsGeometry.fromPointXY(point))
                    new_layer.addFeature(new_feature)
                    new_points.append(point)

    if new_points:
        QgsMessageLog.logMessage(
            f"Added {len(new_points)} unconnected endpoints to the layer.",
            "Success",
            level=Qgis.Success,
        )
    else:
        QgsMessageLog.logMessage(
            "No unconnected endpoints found.",
            "Warning",
            level=Qgis.Warning,
        )

    # Commit the changes to the new layer
    new_layer.commitChanges()
