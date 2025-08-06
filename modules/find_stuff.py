"""Module: find_stuff.py

This module contains the functions that find thnigs in the selected layer.
"""

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsRectangle,
    QgsVectorLayer,
    QgsWkbTypes,
)

from .general import log_debug

SEARCH_RADIUS: float = 0.05


def unconnected_endpoints(
    selected_layer: QgsVectorLayer, new_layer: QgsVectorLayer
) -> None:
    """Find the endpoints of lines that are not connected to other lines."""
    features_checked: int = 0
    new_points: int = 0

    # Start editing the new layer
    new_layer.startEditing()

    for feature in selected_layer.getFeatures() or []:
        features_checked += 1
        geom: QgsGeometry = feature.geometry()

        for part in geom.constParts() or []:
            if part.wkbType() not in [
                QgsWkbTypes.LineString,
                QgsWkbTypes.LineStringZ,
                QgsWkbTypes.LineStringM,
                QgsWkbTypes.LineStringZM,
            ]:
                continue

            if part.vertexCount() < 2:
                continue

            for point in [part.startPoint(), part.endPoint()]:
                # Create a small buffer around the point to search for other lines
                search_rect: QgsRectangle = (
                    QgsGeometry.fromPoint(point).buffer(SEARCH_RADIUS, 5).boundingBox()
                )

                # Refine the selection with a more precise intersection check
                search_geom: QgsGeometry = QgsGeometry.fromPoint(point).buffer(
                    SEARCH_RADIUS, 5
                )
                request: QgsFeatureRequest = QgsFeatureRequest().setFilterRect(
                    search_rect
                )
                intersecting_ids: list[int] = [
                    f.id()
                    for f in selected_layer.getFeatures(request) or []
                    if f.geometry().intersects(search_geom)
                ]
                # Remove the current feature's ID from the list of intersecting features
                if feature.id() in intersecting_ids:
                    intersecting_ids.remove(feature.id())

                # If no other line is found, then the endpoint is unconnected
                if not intersecting_ids:
                    new_feature = QgsFeature(new_layer.fields())
                    new_feature.setGeometry(QgsGeometry.fromPoint(point))
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
        log_debug(
            f"{features_checked} lines checked. "
            f"{new_points} unconnected endpoints found.",
            Qgis.Success,
        )
    else:
        log_debug(
            f"{features_checked} lines checked. No unconnected endpoints found.",
            Qgis.Warning,
        )

    # Commit the changes to the new layer
    new_layer.commitChanges()
