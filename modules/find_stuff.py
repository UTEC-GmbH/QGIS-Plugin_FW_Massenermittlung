"""Module: find_stuff.py

This module contains the FeatureFinder class that finds things in the selected layer.
"""

from enum import Flag, auto
from typing import TYPE_CHECKING

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
from qgis.PyQt.QtCore import QCoreApplication  # type: ignore[reportMissingTypeStubs]

from . import constants as cont
from . import general

if TYPE_CHECKING:
    from qgis.core import QgsRectangle


class FeatureType(Flag):
    """Enum for the types of features to find."""

    NONE = 0
    T_PIECES = auto()
    HOUSES = auto()
    BENDS = auto()
    REDUCERS = auto()


class FeatureFinder:
    """A class to find different types of features in a vector layer."""

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

    def find_features(self, feature_to_search: FeatureType) -> dict[str, int]:
        """Find features based on the provided flags.

        :param feature_types: A flag combination of the features to find.
        :returns: A dictionary with the count of found features.
        """
        t_pieces: str = QCoreApplication.translate("general", "T-pieces")
        houses: str = QCoreApplication.translate("general", "houses")
        bends: str = QCoreApplication.translate("general", "bends")
        reducers: str = QCoreApplication.translate("general", "reducers")

        found_counts: dict[str, int] = {
            t_pieces: 0,
            houses: 0,
            bends: 0,
            reducers: 0,
        }

        if not self.new_layer.startEditing():
            general.raise_runtime_error(
                QCoreApplication.translate(
                    "RuntimeError", "Failed to start editing the new layer."
                )
            )

        if FeatureType.T_PIECES in feature_to_search:
            found_counts[t_pieces] = self._find_t_pieces(self.selected_layer_features)
        if FeatureType.HOUSES in feature_to_search:
            found_counts[houses] = self._find_house_connections(
                self.selected_layer_features
            )
        if FeatureType.BENDS in feature_to_search:
            found_counts[bends] = self._find_bends(self.selected_layer_features)

        if not self.new_layer.commitChanges():
            general.raise_runtime_error(
                QCoreApplication.translate(
                    "RuntimeError", "Failed to commit changes to the new layer."
                )
            )

        return found_counts

    def _get_all_features(self) -> list[QgsFeature]:
        """Get all features from the selected layer."""
        self.selected_layer.selectAll()

        features: list[QgsFeature] = list(self.selected_layer.selectedFeatures())
        if not features:
            general.raise_runtime_error(
                QCoreApplication.translate(
                    "RuntimeError", "No features found in the selected layer."
                )
            )
        general.log_debug(
            QCoreApplication.translate(
                "log", "Found {0} lines in the selected layer."
            ).format(len(features)),
            Qgis.Success,
        )
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
            cont.Numbers.search_radius, 5
        )
        search_rect: QgsRectangle = search_geom.boundingBox()
        request: QgsFeatureRequest = QgsFeatureRequest().setFilterRect(search_rect)

        candidates = iter(self.selected_layer.getFeatures(request))
        if candidates is not None:
            return [
                feat.id()
                for feat in candidates
                if feat.id() != current_feature_id
                and feat.geometry().intersects(search_geom)
            ]
        return []

    def _create_feature(self, geometry: QgsGeometry, attributes: dict) -> bool:
        """Create a new feature in the new layer."""
        new_feature = QgsFeature(self.new_layer.fields())
        new_feature.setGeometry(geometry)

        for field_name, value in attributes.items():
            new_feature.setAttribute(field_name, value)

        return self.new_layer.addFeature(new_feature)

    def _get_connected_attributes(self, connected_features: list[QgsFeature]) -> dict:
        """Get attributes from connected features."""
        connected_ids: list[str] = sorted({str(f.id()) for f in connected_features})
        attributes: dict = {
            cont.NewLayerFields.connected.name: cont.Names.line_separator.join(
                connected_ids
            )
        }
        # Get dimension values if the field exists
        dim_field: str = cont.Names.sel_layer_field_dim
        if self.selected_layer.fields().lookupField(dim_field) != -1:
            dims: list[str] = sorted(
                {
                    f"{cont.Names.dim_prefix}{feat[dim_field]}"
                    for feat in connected_features
                    if feat.attribute(dim_field) is not None
                }
            )
            attributes[cont.NewLayerFields.dimensions.name] = (
                cont.Names.dim_separator.join(dims)
            )

        return attributes

    def _find_house_connections(self, features: list[QgsFeature]) -> int:
        """Find the endpoints of lines that are not connected to other lines."""
        number_of_new_points = 0
        for feature in features:
            for point in self._get_start_end_of_line(feature):
                intersecting_ids: list[int] = self._find_intersecting_feature_ids(
                    point, feature.id()
                )
                if not intersecting_ids:
                    attributes = {
                        cont.NewLayerFields.type.name: cont.Names.attr_val_type_house
                    }
                    attributes |= self._get_connected_attributes([feature])
                    if self._create_feature(QgsGeometry.fromPointXY(point), attributes):
                        number_of_new_points += 1

        general.log_summary(
            QCoreApplication.translate("log", "house connections"),
            len(features),
            number_of_new_points,
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
        search_rect: QgsRectangle = search_geom.boundingBox()
        candidate_ids: list[int] = self.selected_layer_index.intersects(search_rect)
        return [
            self.selected_layer.getFeature(feat_id)
            for feat_id in candidate_ids
            if self.selected_layer.getFeature(feat_id)
            .geometry()
            .intersects(search_geom)
        ]

    def _find_t_pieces(self, features: list[QgsFeature]) -> int:
        """Find 3-way (or more) intersections of lines."""
        number_of_new_points = 0
        checked_intersections: set = set()
        dim_field: str = cont.Names.sel_layer_field_dim

        for feature in features:
            geom: QgsGeometry = feature.geometry()
            candidate_ids: list[int] = self.selected_layer_index.intersects(
                geom.boundingBox().buffered(cont.Numbers.search_radius)
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
                ).buffer(cont.Numbers.search_radius, 5)
                intersecting_features: list[QgsFeature] = (
                    self._get_intersecting_features(search_geom)
                )

                if len(intersecting_features) >= cont.Numbers.min_intersec_t:
                    attributes: dict[str, str] = {
                        cont.NewLayerFields.type.name: cont.Names.attr_val_type_t_piece
                    }
                    attributes |= self._get_connected_attributes(intersecting_features)
                    if self._create_feature(intersection, attributes):
                        number_of_new_points += 1

                    # Add reducers if dimensions differ
                    dimensions: dict[int, float] = {}
                    for f in intersecting_features:
                        dim_val = f.attribute(dim_field)
                        if dim_val is not None:
                            try:
                                dimensions[f.id()] = float(dim_val)
                            except (ValueError, TypeError):
                                general.log_debug(
                                    f"Could not parse dimension '{dim_val}' for feature {f.id()}"
                                )

                    if not dimensions:
                        continue

                    max_dim: float = max(dimensions.values())

                    for f in intersecting_features:
                        f_id: int = f.id()
                        if f_id not in dimensions:
                            continue

                        line_dim: float = dimensions[f_id]

                        if line_dim < max_dim:
                            line_geom: QgsGeometry = f.geometry()
                            if not line_geom or line_geom.isNull():
                                continue

                            line_points: list[QgsPointXY] = line_geom.asPolyline()
                            if not line_points:
                                continue

                            start_point: QgsPointXY = QgsPointXY(line_points[0])
                            end_point: QgsPointXY = QgsPointXY(line_points[-1])

                            dist_to_start: float = intersection_point.distance(
                                start_point
                            )
                            dist_to_end: float = intersection_point.distance(end_point)

                            reducer_point: QgsPointXY | None = None
                            if dist_to_start < cont.Numbers.search_radius:
                                if line_geom.length() > cont.Numbers.distance_t_reducer:
                                    reducer_geom: QgsGeometry = line_geom.interpolate(
                                        cont.Numbers.distance_t_reducer
                                    )
                                    reducer_point = reducer_geom.asPoint()
                            elif dist_to_end < cont.Numbers.search_radius:
                                if line_geom.length() > cont.Numbers.distance_t_reducer:
                                    reducer_geom: QgsGeometry = line_geom.interpolate(
                                        line_geom.length()
                                        - cont.Numbers.distance_t_reducer
                                    )
                                    reducer_point = reducer_geom.asPoint()

                            if reducer_point:
                                reducer_attributes: dict[str, str] = {
                                    cont.NewLayerFields.type.name: cont.Names.attr_val_type_reducer,
                                    cont.NewLayerFields.dimensions.name: f"{cont.Names.dim_prefix}{int(max_dim)}/{cont.Names.dim_prefix}{int(line_dim)}",
                                    cont.NewLayerFields.connected.name: str(f.id()),
                                }
                                self._create_feature(
                                    QgsGeometry.fromPointXY(reducer_point),
                                    reducer_attributes,
                                )

        general.log_summary(
            QCoreApplication.translate("log", "T-pieces"),
            len(features),
            number_of_new_points,
        )
        return number_of_new_points

    @staticmethod
    def _calculate_angle(p1: QgsPointXY, p2: QgsPointXY, p3: QgsPointXY) -> float:
        """Calculate the angle between three points in degrees using azimuths."""

        # Check for coincident points which would make angle calculation invalid.
        if p2.compare(p1, cont.Numbers.tiny_number) or p2.compare(
            p3, cont.Numbers.tiny_number
        ):
            general.log_debug("Coinciding points found.", Qgis.Warning)
            return 0.0

        azimuth1: float = p2.azimuth(p1)
        azimuth2: float = p2.azimuth(p3)

        angle: float = abs(azimuth1 - azimuth2)

        if angle > cont.Numbers.circle_semi:
            angle = cont.Numbers.circle_full - angle

        return cont.Numbers.circle_semi - angle

    def _is_t_piece(self, point: QgsPointXY) -> bool:
        """Check if a point is a T-intersection."""
        search_geom: QgsGeometry = QgsGeometry.fromPointXY(point).buffer(
            cont.Numbers.search_radius, 5
        )
        intersecting_features: list[QgsFeature] = self._get_intersecting_features(
            search_geom
        )
        return len(intersecting_features) >= cont.Numbers.min_intersec_t

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

    def _find_bends(self, features: list[QgsFeature]) -> int:
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

        general.log_summary(
            QCoreApplication.translate("log", "bends"),
            len(features),
            number_of_new_points,
        )
        return number_of_new_points
