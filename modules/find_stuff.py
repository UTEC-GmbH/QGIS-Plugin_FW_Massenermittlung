"""Module: find_stuff.py

This module contains the functions that find thnigs in the selected layer.
"""

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
    QgsSpatialIndex,
    QgsVectorLayer,
    QgsWkbTypes,
)

from .general import log_debug, raise_runtime_error

SEARCH_RADIUS: float = 0.05
T_ST_BUFFER: float = 0.01


def get_all_features(layer: QgsVectorLayer) -> list[QgsFeature]:
    """Get all features from a QgsVectorLayer.

    :param layer: The QgsVectorLayer to get features from.
    :returns: A list of QgsFeature objects.
    """

    features: list[QgsFeature] = list(layer.getFeatures())
    if not features:
        raise_runtime_error("No features found in the selected layer.")

    return features


def get_start_end_of_line(feature: QgsFeature) -> list[QgsPointXY]:
    """Get the start and end of a line.

    :param feature: The QgsFeature to get the start and end of.
    :returns: A list of the start and end points of the line parts as QgsPointXY.
    """

    points: list = []
    geom: QgsGeometry = feature.geometry()
    if not geom:
        return points

    wkb_type: Qgis.WkbType = geom.wkbType()

    lines = []
    if wkb_type == QgsWkbTypes.LineString:
        lines.append(geom.asPolyline())
    elif wkb_type == QgsWkbTypes.MultiLineString:
        lines.extend(geom.asMultiPolyline())

    for line in lines:
        if len(line) > 1:
            points.extend([line[0], line[-1]])
    return points


def find_intersecting_feature_ids(
    point: QgsPointXY,
    selected_layer: QgsVectorLayer,
    current_feature_id: int,
) -> list[int]:
    """Find intersecting feature IDs for a given point, excluding the current feature.

    :param point: The QgsPoint to search around.
    :param selected_layer: The QgsVectorLayer to search within.
    :param current_feature_id: The ID of the feature to exclude from the results.
    :returns: A list of feature IDs that intersect with the search geometry,
              excluding the `current_feature_id`.
    """
    search_geom: QgsGeometry = QgsGeometry.fromPointXY(point).buffer(SEARCH_RADIUS, 5)
    search_rect: QgsRectangle = search_geom.boundingBox()
    request: QgsFeatureRequest = QgsFeatureRequest().setFilterRect(search_rect)

    candidates: list = list(selected_layer.getFeatures(request))
    if not candidates:
        return []

    intersecting_ids: list[int] = [
        feat.id()
        for feat in candidates
        if feat.id() != current_feature_id and feat.geometry().intersects(search_geom)
    ]

    return intersecting_ids


def create_feature(
    geometry: QgsGeometry,
    source_feature: QgsFeature,
    new_layer: QgsVectorLayer,
    attributes: dict,
) -> bool:
    """Create a new feature in a QgsVectorLayer.

    :param geometry: The QgsGeometry for the new feature.
    :param source_feature: The source QgsFeature from which attributes will be copied.
    :param new_layer: The QgsVectorLayer to which the new feature will be added.
    :param attributes: A dictionary of additional attributes to set for the new feature.
                       These attributes will override any attributes with the same name
                       copied from the source_feature.
    :returns: True if the feature was successfully added, False otherwise.
    """
    new_feature = QgsFeature(new_layer.fields())
    new_feature.setGeometry(geometry)

    new_fields = new_layer.fields()
    source_field_names = {f.name() for f in source_feature.fields()}

    attributes_list = []
    for field in new_fields:
        field_name = field.name()
        if field_name in source_field_names:
            attributes_list.append(source_feature.attribute(field_name))
        else:
            attributes_list.append(None)

    for field_name, value in attributes.items():
        field_index = new_fields.indexOf(field_name)
        if field_index != -1:
            attributes_list[field_index] = value

    new_feature.setAttributes(attributes_list)

    return new_layer.addFeature(new_feature)


def unconnected_endpoints(
    selected_layer: QgsVectorLayer, new_layer: QgsVectorLayer
) -> int:
    """Find the endpoints of lines that are not connected to other lines."""
    features_checked: int = 0
    number_of_new_points: int = 0

    # Start editing the new layer
    if not new_layer.startEditing():
        raise_runtime_error("Failed to start editing the new layer.")

    for feature in get_all_features(selected_layer):
        features_checked += 1

        for point in get_start_end_of_line(feature):
            intersecting_ids = find_intersecting_feature_ids(
                point, selected_layer, feature.id()
            )

            if not intersecting_ids and create_feature(
                QgsGeometry.fromPointXY(point),
                feature,
                new_layer,
                {"Typ": "Hausanschluss"},
            ):
                number_of_new_points += 1

    if number_of_new_points:
        log_debug(
            f"Hausanschlüsse: {features_checked} Linien geprüft → "
            f"{number_of_new_points} Hausanschlüsse gefunden.",
            Qgis.Success,
        )
    else:
        log_debug(
            f"Hausanschlüsse: {features_checked} Linien geprüft, "
            f"aber keine Hausanschlüsse gefunden!",
            Qgis.Warning,
        )

    # Commit the changes to the new layer
    if not new_layer.commitChanges():
        raise_runtime_error("Failed to commit changes to the new layer.")

    return number_of_new_points


def line_intersections(
    selected_layer: QgsVectorLayer, new_layer: QgsVectorLayer
) -> int:
    """Find 3-way (or more) intersections of lines in the selected layer."""
    number_of_new_points: int = 0

    # Create a spatial index for the selected layer
    index = QgsSpatialIndex(selected_layer.getFeatures())

    # Start editing the new layer
    if not new_layer.startEditing():
        raise_runtime_error("Failed to start editing the new layer.")

    # Iterate over each feature in the selected layer
    for feature in get_all_features(selected_layer):
        geom = feature.geometry()

        # Find candidate intersecting features using the spatial index
        candidate_ids = index.intersects(geom.boundingBox().buffered(T_ST_BUFFER))

        # Check for actual intersections
        for candidate_id in candidate_ids:
            if candidate_id == feature.id():
                continue

            candidate_feature = selected_layer.getFeature(candidate_id)
            candidate_geom = candidate_feature.geometry()

            if geom.intersects(candidate_geom):
                intersection = geom.intersection(candidate_geom)

                # Check if the intersection is a point
                if intersection.wkbType() == QgsWkbTypes.Point:
                    # Buffer the intersection point to find nearby lines
                    search_geom = intersection.buffer(T_ST_BUFFER, 5)
                    search_rect = search_geom.boundingBox()
                    request = QgsFeatureRequest().setFilterRect(search_rect)

                    # Find all features that intersect with the intersection point
                    intersecting_features = [
                        f
                        for f in selected_layer.getFeatures(request)
                        if f.geometry().intersects(search_geom)
                    ]

                    # If we have a 3-way (or more) intersection, create a new point
                    if len(intersecting_features) >= 3 and create_feature(
                        intersection,
                        feature,
                        new_layer,
                        {"Typ": "T-Stück"},
                    ):
                        number_of_new_points += 1
    if number_of_new_points:
        log_debug(
            f"T-Stücke: {len(get_all_features(selected_layer))} Linien geprüft → "
            f"{number_of_new_points} T-Stücke gefunden.",
            Qgis.Success,
        )
    else:
        log_debug(
            f"T-Stücke: {len(get_all_features(selected_layer))} Linien geprüft, "
            f"aber keine T-Stücke gefunden!",
            Qgis.Warning,
        )

    # Commit the changes to the new layer
    if not new_layer.commitChanges():
        raise_runtime_error("Failed to commit changes to the new layer.")

    return number_of_new_points
