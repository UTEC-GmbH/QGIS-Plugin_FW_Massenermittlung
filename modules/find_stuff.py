"""Module: find_stuff.py

This module contains the functions that find thnigs in the selected layer.
"""

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsMessageLog,
    QgsRectangle,
    QgsSpatialIndex,
    QgsVectorLayer,
)
from qgis.gui import QgisInterface

from .general import LayerManager

SEARCH_RADIUS: float = 0.05


def find_unconnected_endpoints(plugin: QgisInterface) -> None:
    """Find the endpoints of lines that are not connected to other lines."""
    features_checked: int = 0
    new_points: int = 0
    layer_manager = LayerManager(plugin)
    selected_layer: QgsVectorLayer = layer_manager.selected_layer
    new_layer: QgsVectorLayer = layer_manager.new_layer

    # Create a spatial index for the selected layer
    index = QgsSpatialIndex(selected_layer.getFeatures())

    # Start editing the new layer
    new_layer.startEditing()

    for feature in selected_layer.getFeatures():
        features_checked += 1
        geom: QgsGeometry = feature.geometry()

        lines = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
        for line in lines:
            for point in [line[0], line[-1]]:
                # Create a small buffer around the point to search for other lines
                search_rect: QgsRectangle = (
                    QgsGeometry.fromPointXY(point)
                    .buffer(SEARCH_RADIUS, 5)
                    .boundingBox()
                )
                candidate_ids: list[int] = index.intersects(search_rect)

                # Refine the selection with a more precise intersection check
                search_geom: QgsGeometry = QgsGeometry.fromPointXY(point).buffer(
                    SEARCH_RADIUS, 5
                )
                request = QgsFeatureRequest().setFilterFids(candidate_ids)
                intersecting_ids: list[int] = []
                for f in selected_layer.getFeatures(request):
                    if f.geometry().intersects(search_geom):
                        intersecting_ids.append(f.id())

                # Remove the current feature's ID from the list of intersecting features
                if feature.id() in intersecting_ids:
                    intersecting_ids.remove(feature.id())

                # If no other line is found, then the endpoint is unconnected
                if not intersecting_ids:
                    new_feature = QgsFeature(new_layer.fields())
                    new_feature.setGeometry(QgsGeometry.fromPointXY(point))
                    new_feature.setAttribute("Typ", "Hausanschluss")

                    # Copy attributes from the source feature to the new feature
                    for field in feature.fields():
                        if new_feature.fields().indexOf(field.name()) != -1:
                            new_feature.setAttribute(
                                field.name(), feature.attribute(field.name())
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
