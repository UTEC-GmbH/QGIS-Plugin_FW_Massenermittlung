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

from .general import log_debug, raise_runtime_error

SEARCH_RADIUS: float = 0.05


def get_all_features(layer: QgsVectorLayer) -> list:
    """Get all features from a QgsVectorLayer.

    :param layer: The QgsVectorLayer to get features from.
    :returns: A list of QgsFeature objects.
    """
    features: list = list(layer.getFeatures())
    if not features:
        raise_runtime_error("No features found in the selected layer.")

    return features


def get_start_end_of_line(feature: QgsFeature) -> list:
    """Get the start and end of a line.

    :param feature: The QgsFeature to get the start and end of.
    :returns: A list of the start and end points of the line parts.
    """

    points: list = []
    geom: QgsGeometry = feature.geometry()
    if not geom:
        return points

    parts: list = list(geom.constParts())

    for part in parts:
        if part.wkbType() in [
            QgsWkbTypes.LineString,
            QgsWkbTypes.LineStringZ,
            QgsWkbTypes.LineStringM,
            QgsWkbTypes.LineStringZM,
        ]:
            points.extend([part.startPoint(), part.endPoint()])
    return points


def find_intersecting_feature_ids(
    point: "QgsPoint",
    selected_layer: QgsVectorLayer,
    current_feature_id: int,
) -> list[int]:
    """Find intersecting feature IDs for a given point, excluding the current feature."""
    search_geom: QgsGeometry = QgsGeometry.fromPoint(point).buffer(SEARCH_RADIUS, 5)
    search_rect: QgsRectangle = search_geom.boundingBox()
    request: QgsFeatureRequest = QgsFeatureRequest().setFilterRect(search_rect)

    candidates: list = list(selected_layer.getFeatures(request))
    if not candidates:
        return []

    intersecting_ids: list[int] = [
        feat.id() for feat in candidates if feat.geometry().intersects(search_geom)
    ]

    # Remove the current feature's ID from the list of intersecting features
    if current_feature_id in intersecting_ids:
        intersecting_ids.remove(current_feature_id)

    return intersecting_ids


def create_feature(
    geometry: QgsGeometry,
    source_feature: QgsFeature,
    new_layer: QgsVectorLayer,
    attributes: dict,
) -> bool:
    """Create a new feature in a layer."""
    new_feature = QgsFeature(new_layer.fields())
    new_feature.setGeometry(geometry)

    for key, value in attributes.items():
        new_feature.setAttribute(key, value)

    # Copy attributes from the source feature to the new feature
    for field in source_feature.fields():
        if new_layer.fields().indexOf(field.name()) != -1:
            new_feature.setAttribute(
                field.name(), source_feature.attribute(field.name())
            )

    return new_layer.addFeature(new_feature)


def unconnected_endpoints(
    selected_layer: QgsVectorLayer, new_layer: QgsVectorLayer
) -> None:
    """Find the endpoints of lines that are not connected to other lines."""
    features_checked: int = 0
    new_points: int = 0

    # Start editing the new layer
    new_layer.startEditing()

    for feature in get_all_features(selected_layer):
        features_checked += 1

        for point in get_start_end_of_line(feature):
            intersecting_ids = find_intersecting_feature_ids(
                point, selected_layer, feature.id()
            )

            if not intersecting_ids and create_feature(
                QgsGeometry.fromPoint(point),
                feature,
                new_layer,
                {"Typ": "Hausanschluss"},
            ):
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
