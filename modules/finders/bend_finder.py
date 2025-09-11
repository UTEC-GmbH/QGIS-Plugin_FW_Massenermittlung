"""Module: bend_finder.py

This module contains the BendFinder class.
"""

from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsWkbTypes
from qgis.PyQt.QtCore import (
    QCoreApplication,  # type: ignore[reportAttributeAccessIssue]
)

from modules import constants as cont
from modules.logs_and_errors import log_summary

from .base_finder import BaseFinder


class BendFinder(BaseFinder):
    """A class to find bends."""

    def find(self, features: list[QgsFeature]) -> int:
        """Find angles in lines and at intersections."""
        number_of_new_points = 0
        checked_points: set = set()

        # Part 1: Find internal angles
        for feature in features:
            internal_bends: list[tuple[QgsPointXY, float]] = self._get_internal_angles(
                feature
            )
            for point, angle in internal_bends:
                key: tuple[float, float] = (round(point.x(), 4), round(point.y(), 4))
                if key in checked_points:
                    continue

                if not self._is_t_piece(point):
                    attributes = {
                        cont.NewLayerFields.type.name: cont.Names.attr_val_type_bend,
                        cont.NewLayerFields.angle.name: angle,
                    }
                    attributes |= self._get_connected_attributes([feature])
                    if self._create_feature(QgsGeometry.fromPointXY(point), attributes):
                        number_of_new_points += 1

                checked_points.add(key)

        # Part 2: Find intersection angles
        for i, feature1 in enumerate(features):
            for j in range(i + 1, len(features)):
                feature2: QgsFeature = features[j]
                intersection_bends: list[tuple[QgsPointXY, float]] = (
                    self._get_intersection_angles(feature1, feature2)
                )
                for point, angle in intersection_bends:
                    key = (round(point.x(), 4), round(point.y(), 4))
                    if key in checked_points:
                        continue

                    if not self._is_t_piece(point):
                        attributes = {
                            cont.NewLayerFields.type.name: cont.Names.attr_val_type_bend,
                            cont.NewLayerFields.angle.name: round(angle, 2),
                        }
                        attributes |= self._get_connected_attributes(
                            [feature1, feature2]
                        )
                        if self._create_feature(
                            QgsGeometry.fromPointXY(point), attributes
                        ):
                            number_of_new_points += 1

                    checked_points.add(key)

        log_summary(
            QCoreApplication.translate("log", "bends"),
            len(features),
            number_of_new_points,
        )
        return number_of_new_points

    def _get_internal_angles(
        self, feature: QgsFeature
    ) -> list[tuple[QgsPointXY, float]]:
        """Find all angles at vertices and joints within a single feature."""

        geom: QgsGeometry = feature.geometry()
        if not geom or geom.wkbType() not in [
            QgsWkbTypes.LineString,
            QgsWkbTypes.MultiLineString,
        ]:
            return []

        lines: list = (
            geom.asMultiPolyline()
            if geom.wkbType() == QgsWkbTypes.MultiLineString
            else [geom.asPolyline()]
        )

        vertex_map: dict = {}
        for line in lines:
            if len(line) < cont.Numbers.min_points_line:
                continue
            for i, point in enumerate(line):
                key: tuple = (round(point.x(), 4), round(point.y(), 4))
                vertex_map.setdefault(key, {"p": point, "connections": set()})
                if i > 0:
                    vertex_map[key]["connections"].add(line[i - 1])
                if i < len(line) - 1:
                    vertex_map[key]["connections"].add(line[i + 1])

        bends: list = []
        for data in vertex_map.values():
            connections: list = list(data["connections"])
            if len(connections) == cont.Numbers.min_intersec:
                p2 = data["p"]
                p1, p3 = connections[0], connections[1]
                angle: float = self._calculate_angle(p1, p2, p3)

                if angle >= cont.Numbers.min_angle_bogen:
                    bends.append((p2, angle))
        return bends

    def _get_intersection_angles(
        self, feature1: QgsFeature, feature2: QgsFeature
    ) -> list[tuple[QgsPointXY, float]]:
        """Find all intersection angles between two features."""
        geom1: QgsGeometry = feature1.geometry()
        geom2: QgsGeometry = feature2.geometry()

        if not geom1 or not geom2 or not geom1.intersects(geom2):
            return []

        intersection: QgsGeometry = geom1.intersection(geom2)
        if intersection.isEmpty() or intersection.wkbType() not in [
            QgsWkbTypes.Point,
            QgsWkbTypes.MultiPoint,
        ]:
            return []

        points: list = (
            intersection.asMultiPoint()
            if intersection.wkbType() == QgsWkbTypes.MultiPoint
            else [intersection.asPoint()]
        )

        bends: list = []
        for p_intersect in points:
            dist_sq1, _, after_v1, __ = geom1.closestSegmentWithContext(p_intersect)
            dist_sq2, _, after_v2, __ = geom2.closestSegmentWithContext(p_intersect)

            if (
                dist_sq1 < cont.Numbers.search_radius
                and dist_sq2 < cont.Numbers.search_radius
            ):
                p1_start: QgsPointXY = QgsPointXY(geom1.vertexAt(after_v1 - 1))
                p1_end: QgsPointXY = QgsPointXY(geom1.vertexAt(after_v1))
                p1: QgsPointXY = (
                    p1_end
                    if p1_start.distance(p_intersect) < cont.Numbers.tiny_number
                    else p1_start
                )

                p3_start: QgsPointXY = QgsPointXY(geom2.vertexAt(after_v2 - 1))
                p3_end: QgsPointXY = QgsPointXY(geom2.vertexAt(after_v2))
                p3: QgsPointXY = (
                    p3_end
                    if p3_start.distance(p_intersect) < cont.Numbers.tiny_number
                    else p3_start
                )

                angle: float = self._calculate_angle(p1, p_intersect, p3)

                if angle >= cont.Numbers.min_angle_bogen:
                    bends.append((p_intersect, angle))

        return bends
