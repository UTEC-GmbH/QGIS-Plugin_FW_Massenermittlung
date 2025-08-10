"""Module: find_stuff.py

This module contains the FeatureFinder class that finds things in the selected layer.
"""

import math
from enum import Flag, auto

from qgis._core import QgsFields, QgsRectangle
from qgis.core import (
    Qgis,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsPoint,
    QgsPointXY,
    QgsSpatialIndex,
    QgsVectorLayer,
    QgsWkbTypes,
)

from .general import log_debug, log_summary, raise_runtime_error


class FeatureType(Flag):
    """Enum for the types of features to find."""

    NONE = 0
    T_STUECKE = auto()
    HAUSANSCHLUESSE = auto()
    BOEGEN = auto()


class FeatureFinder:
    """A class to find different types of features in a vector layer."""

    MIN_POINTS_LINE: int = 2
    MIN_POINTS_MULTILINE: int = 3
    SEARCH_RADIUS: float = 0.05
    T_ST_MIN_INTERSEC: int = 3
    BOEGEN_MIN_ANGLE: int = 15

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
            found_counts["T-Stücke"] = self._find_t_stuecke(
                self.selected_layer_features
            )
        if FeatureType.HAUSANSCHLUESSE in feature_types:
            found_counts["Hausanschlüsse"] = self._find_hausanschluesse(
                self.selected_layer_features
            )
        if FeatureType.BOEGEN in feature_types:
            found_counts["Bögen"] = self._find_boegen(self.selected_layer_features)

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
        source_field_names: set = {field.name() for field in source_feature.fields()}

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

    def _find_hausanschluesse(self, features: list[QgsFeature]) -> int:
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

        log_summary("Hausanschlüsse", len(features), number_of_new_points)
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

    def _find_t_stuecke(self, features: list[QgsFeature]) -> int:
        """Find 3-way (or more) intersections of lines."""
        number_of_new_points = 0
        checked_intersections: set = set()

        for feature in features:
            geom: QgsGeometry = feature.geometry()
            candidate_ids: list[int] = self.selected_layer_index.intersects(
                geom.boundingBox().buffered(self.SEARCH_RADIUS)
            )

            for candidate_id in candidate_ids:
                if candidate_id <= feature.id():
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
                ).buffer(self.SEARCH_RADIUS, 5)
                intersecting_features: list[QgsFeature] = (
                    self._get_intersecting_features(search_geom)
                )

                if len(
                    intersecting_features
                ) >= self.T_ST_MIN_INTERSEC and self._create_feature(
                    intersection, feature, {"Typ": "T-Stück"}
                ):
                    number_of_new_points += 1

        log_summary("T-Stücke", len(features), number_of_new_points)
        return number_of_new_points

    @staticmethod
    def _calculate_angle(p1: QgsPointXY, p2: QgsPointXY, p3: QgsPointXY) -> float:
        """Calculate the angle between three points in degrees."""
        v1: tuple[float, float] = (p1.x() - p2.x(), p1.y() - p2.y())
        v2: tuple[float, float] = (p3.x() - p2.x(), p3.y() - p2.y())

        dot_product: float = v1[0] * v2[0] + v1[1] * v2[1]
        mag_v1: float = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
        mag_v2: float = math.sqrt(v2[0] ** 2 + v2[1] ** 2)

        if mag_v1 == 0 or mag_v2 == 0:
            return 0.0

        cosine_angle: float = dot_product / (mag_v1 * mag_v2)
        angle: float = math.degrees(math.acos(max(min(cosine_angle, 1.0), -1.0)))
        return 180 - angle

    def _is_t_stueck(self, point: QgsPointXY) -> bool:
        """Check if a point is a T-intersection."""
        search_geom = QgsGeometry.fromPointXY(point).buffer(self.SEARCH_RADIUS, 5)
        intersecting_features = self._get_intersecting_features(search_geom)
        return len(intersecting_features) >= self.T_ST_MIN_INTERSEC

    def _get_internal_angles(
        self, feature: QgsFeature
    ) -> list[tuple[QgsPointXY, float]]:
        """Find all angles at vertices and joints within a single feature."""

        geom = feature.geometry()
        if not geom or geom.wkbType() not in [
            QgsWkbTypes.LineString,
            QgsWkbTypes.MultiLineString,
        ]:
            return []

        lines = (
            geom.asMultiPolyline()
            if geom.wkbType() == QgsWkbTypes.MultiLineString
            else [geom.asPolyline()]
        )

        vertex_map = {}
        for line in lines:
            if len(line) < 2:
                continue
            for i, point in enumerate(line):
                key = (round(point.x(), 4), round(point.y(), 4))
                vertex_map.setdefault(key, {"p": point, "connections": set()})
                if i > 0:
                    vertex_map[key]["connections"].add(line[i - 1])
                if i < len(line) - 1:
                    vertex_map[key]["connections"].add(line[i + 1])

        bends = []
        bends_debug = []
        for data in vertex_map.values():
            connections = list(data["connections"])
            if len(connections) == 2:
                p2 = data["p"]
                p1, p3 = connections[0], connections[1]
                angle = self._calculate_angle(p1, p2, p3)
                bends_debug.append((p2, angle))
                if angle >= self.BOEGEN_MIN_ANGLE:
                    bends.append((p2, angle))

        log_debug(
            f"Internal angles for feature '{feature.id()}': {bends_debug}", Qgis.Info
        )

        return bends

    def _get_intersection_angles(
        self, feature1: QgsFeature, feature2: QgsFeature
    ) -> list[tuple[QgsPointXY, float]]:
        """Find all intersection angles between two features."""
        geom1 = feature1.geometry()
        geom2 = feature2.geometry()

        if not geom1 or not geom2 or not geom1.intersects(geom2):
            return []

        intersection = geom1.intersection(geom2)
        if intersection.isEmpty() or intersection.wkbType() not in [
            QgsWkbTypes.Point,
            QgsWkbTypes.MultiPoint,
        ]:
            return []

        points = (
            intersection.asMultiPoint()
            if intersection.wkbType() == QgsWkbTypes.MultiPoint
            else [intersection.asPoint()]
        )

        bends = []
        bends_debug = []
        for p_intersect in points:
            dist_sq1, _, after_v1, __ = geom1.closestSegmentWithContext(p_intersect)
            dist_sq2, _, after_v2, __ = geom2.closestSegmentWithContext(p_intersect)

            if dist_sq1 < self.SEARCH_RADIUS and dist_sq2 < self.SEARCH_RADIUS:
                # To avoid calculating an angle of 0, we need to make sure that the
                # points for the angle calculation are not the same as the
                # intersection point. This can happen if the intersection is at a
                # vertex. We get both vertices of the segment and choose the one
                # that is not the intersection point.
                p1_start = geom1.vertexAt(after_v1 - 1)
                p1_end = geom1.vertexAt(after_v1)
                p1 = (
                    p1_end
                    if p1_start.distance(QgsPoint(p_intersect)) < 1e-6
                    else p1_start
                )

                p3_start = geom2.vertexAt(after_v2 - 1)
                p3_end = geom2.vertexAt(after_v2)
                p3 = (
                    p3_end
                    if p3_start.distance(QgsPoint(p_intersect)) < 1e-6
                    else p3_start
                )

                angle = self._calculate_angle(p1, p_intersect, p3)
                bends_debug.append((p_intersect, angle))

                # Get the smallest angle
                if angle > 90:
                    angle = 180 - angle

                if angle >= self.BOEGEN_MIN_ANGLE:
                    bends.append((p_intersect, angle))

        log_debug(
            f"Intersection angles for features '{feature1.id()}' and '{feature2.id()}':"
            f" {bends_debug}",
            Qgis.Info,
        )

        return bends

    def _find_boegen(self, features: list[QgsFeature]) -> int:
        """Find angles in lines and at intersections."""
        number_of_new_points = 0
        checked_points: set = set()

        # Part 1: Find internal angles
        for feature in features:
            internal_bends = self._get_internal_angles(feature)
            for point, angle in internal_bends:
                key = (round(point.x(), 4), round(point.y(), 4))
                if key in checked_points:
                    continue

                if not self._is_t_stueck(point):
                    if self._create_feature(
                        QgsGeometry.fromPointXY(point),
                        feature,
                        {"Typ": "Bogen", "Winkel": round(angle, 2)},
                    ):
                        number_of_new_points += 1

                checked_points.add(key)

        # Part 2: Find intersection angles
        for i, feature1 in enumerate(features):
            for j in range(i + 1, len(features)):
                feature2 = features[j]
                intersection_bends = self._get_intersection_angles(feature1, feature2)
                for point, angle in intersection_bends:
                    key = (round(point.x(), 4), round(point.y(), 4))
                    if key in checked_points:
                        continue

                    if not self._is_t_stueck(point):
                        if self._create_feature(
                            QgsGeometry.fromPointXY(point),
                            feature1,  # or feature2, doesn't matter
                            {"Typ": "Bogen", "Winkel": round(angle, 2)},
                        ):
                            number_of_new_points += 1

                    checked_points.add(key)

        log_summary("Bögen", len(features), number_of_new_points)
        return number_of_new_points
