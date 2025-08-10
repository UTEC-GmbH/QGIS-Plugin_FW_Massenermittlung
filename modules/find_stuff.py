"""Module: find_stuff.py

This module contains the FeatureFinder class that finds things in the selected layer.
"""

from enum import Flag, auto

from qgis._core import QgsFields, QgsRectangle
from qgis.core import (
    Qgis,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPointXY,
    QgsSpatialIndex,
    QgsVectorLayer,
    QgsWkbTypes,
)

from .general import log_debug, raise_runtime_error


class FeatureType(Flag):
    """Enum for the types of features to find."""

    NONE = 0
    T_STUECKE = auto()
    HAUSANSCHLUESSE = auto()
    BOEGEN = auto()


class FeatureFinder:
    """A class to find different types of features in a vector layer."""

    SEARCH_RADIUS: float = 0.05
    T_ST_BUFFER: float = 0.01

    def __init__(
        self, selected_layer: QgsVectorLayer, new_layer: QgsVectorLayer
    ) -> None:
        """Initialize the FeatureFinder class.

        :param selected_layer: The QgsVectorLayer to search within.
        :param new_layer: The QgsVectorLayer to add new features to.
        """
        self.selected_layer: QgsVectorLayer = selected_layer
        self.selected_layer_index: QgsSpatialIndex = QgsSpatialIndex(
            self.selected_layer.getFeatures()
        )
        self.selected_layer_features: list[QgsFeature] = self._get_all_features()

        self.new_layer: QgsVectorLayer = new_layer

    def find_features(self, feature_types: FeatureType) -> dict[str, int]:
        """Find features based on the provided flags.

        :param feature_types: A flag combination of the features to find.
        :returns: A dictionary with the count of found features.
        """
        found_counts: dict[str, int] = {"T-Stücke": 0, "Hausanschlüsse": 0, "Bögen": 0}

        if not self.new_layer.startEditing():
            raise_runtime_error("Failed to start editing the new layer.")

        if FeatureType.T_STUECKE in feature_types:
            found_counts["T-Stücke"] = self._find_line_intersections(
                self.selected_layer_features
            )
        if FeatureType.HAUSANSCHLUESSE in feature_types:
            found_counts["Hausanschlüsse"] = self._find_unconnected_endpoints(
                self.selected_layer_features
            )
        if FeatureType.BOEGEN in feature_types:
            # TODO: Implement angle finding logic
            # found_counts["Bögen"] = self._find_angles(all_features)
            log_debug("Angle detection is not yet implemented.", Qgis.Warning)

        if not self.new_layer.commitChanges():
            raise_runtime_error("Failed to commit changes to the new layer.")

        return found_counts

    def _get_all_features(self) -> list[QgsFeature]:
        """Get all features from the selected layer."""
        features: list[QgsFeature] = list(self.selected_layer.getFeatures())
        if not features:
            raise_runtime_error("No features found in the selected layer.")
        return features

    @staticmethod
    def _get_start_end_of_line(feature: QgsFeature) -> list[QgsPointXY]:
        """Get the start and end points of a line feature."""
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

    def _find_intersecting_feature_ids(
        self, point: QgsPointXY, current_feature_id: int
    ) -> list[int]:
        """Find intersecting feature IDs for a given point."""
        search_geom: QgsGeometry = QgsGeometry.fromPointXY(point).buffer(
            self.SEARCH_RADIUS, 5
        )
        search_rect: QgsRectangle = search_geom.boundingBox()
        request: QgsFeatureRequest = QgsFeatureRequest().setFilterRect(search_rect)

        candidates: list[QgsFeature] = list(self.selected_layer.getFeatures(request))
        if candidates is not None:
            return [
                feat.id()
                for feat in candidates
                if feat.id() != current_feature_id
                and feat.geometry().intersects(search_geom)
            ]
        return []

    def _create_feature(
        self, geometry: QgsGeometry, source_feature: QgsFeature, attributes: dict
    ) -> bool:
        """Create a new feature in the new layer."""
        new_feature = QgsFeature(self.new_layer.fields())
        new_feature.setGeometry(geometry)

        new_fields: QgsFields = self.new_layer.fields()
        source_field_names: set = {f.name() for f in source_feature.fields()}

        attributes_list: list = []
        for field in new_fields:
            field_name: str = field.name()
            if field_name in source_field_names:
                attributes_list.append(source_feature.attribute(field_name))
            else:
                attributes_list.append(None)

        for field_name, value in attributes.items():
            field_index: int = new_fields.indexOf(field_name)
            if field_index != -1:
                attributes_list[field_index] = value

        new_feature.setAttributes(attributes_list)
        return self.new_layer.addFeature(new_feature)

    def _find_unconnected_endpoints(self, features: list[QgsFeature]) -> int:
        """Find the endpoints of lines that are not connected to other lines."""
        number_of_new_points = 0
        for feature in features:
            for point in self._get_start_end_of_line(feature):
                intersecting_ids: list[int] = self._find_intersecting_feature_ids(
                    point, feature.id()
                )
                if not intersecting_ids and self._create_feature(
                    QgsGeometry.fromPointXY(point),
                    feature,
                    {"Typ": "Hausanschluss"},
                ):
                    number_of_new_points += 1

        if number_of_new_points:
            log_debug(
                f"Hausanschlüsse: {len(features)} Linien geprüft → "
                f"{number_of_new_points} Hausanschlüsse gefunden.",
                Qgis.Success,
            )
        else:
            log_debug(
                f"Hausanschlüsse: {len(features)} Linien geprüft, "
                f"aber keine Hausanschlüsse gefunden!",
                Qgis.Warning,
            )
        return number_of_new_points

    @staticmethod
    def _get_point_from_intersection(intersection: QgsGeometry) -> QgsPointXY | None:
        """Extract a QgsPointXY from an intersection geometry."""
        if intersection.wkbType() == QgsWkbTypes.Point:
            return intersection.asPoint()
        if (
            intersection.wkbType() == QgsWkbTypes.MultiPoint
            and not intersection.isEmpty()
        ):
            return intersection.asMultiPoint()[0]
        return None

    def _get_intersecting_features(self, search_geom: QgsGeometry) -> list[QgsFeature]:
        """Get all features intersecting with the given geometry."""
        search_rect: QgsRectangle = search_geom.boundingBox()
        request: QgsFeatureRequest = QgsFeatureRequest().setFilterRect(search_rect)
        return [
            feat
            for feat in list(self.selected_layer.getFeatures(request))
            if feat.geometry().intersects(search_geom)
        ]

    def _find_line_intersections(self, features: list[QgsFeature]) -> int:
        """Find 3-way (or more) intersections of lines."""
        number_of_new_points = 0
        checked_intersections: set = set()

        for feature in features:
            geom: QgsGeometry = feature.geometry()
            candidate_ids: list[int] = self.selected_layer_index.intersects(
                geom.boundingBox().buffered(self.T_ST_BUFFER)
            )

            for candidate_id in candidate_ids:
                if candidate_id <= feature.id():  # Avoid duplicate checks
                    continue

                candidate_feature: QgsFeature = self.selected_layer.getFeature(
                    candidate_id
                )
                candidate_geom: QgsGeometry = candidate_feature.geometry()

                if not geom.intersects(candidate_geom):
                    continue

                intersection: QgsGeometry = geom.intersection(candidate_geom)
                intersection_point: QgsPointXY | None = (
                    self._get_point_from_intersection(intersection)
                )

                if not intersection_point:
                    continue

                point_key: tuple[float, float] = (
                    round(intersection_point.x(), 4),
                    round(intersection_point.y(), 4),
                )
                if point_key in checked_intersections:
                    continue

                checked_intersections.add(point_key)

                search_geom: QgsGeometry = QgsGeometry.fromPointXY(
                    intersection_point
                ).buffer(self.T_ST_BUFFER, 5)
                intersecting_features: list[QgsFeature] = (
                    self._get_intersecting_features(search_geom)
                )

                if len(intersecting_features) >= 3 and self._create_feature(
                    intersection, feature, {"Typ": "T-Stück"}
                ):
                    number_of_new_points += 1

        if number_of_new_points:
            log_debug(
                f"T-Stücke: {len(features)} Linien geprüft → "
                f"{number_of_new_points} T-Stücke gefunden.",
                Qgis.Success,
            )
        else:
            log_debug(
                f"T-Stücke: {len(features)} Linien geprüft, "
                f"aber keine T-Stücke gefunden!",
                Qgis.Warning,
            )
        return number_of_new_points
