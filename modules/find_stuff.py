"""Module: find_stuff.py

This module contains the FeatureFinder class that finds things in the selected layer.
"""

import math
from collections.abc import Callable

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsFeatureRequest,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsSpatialIndex,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QProgressBar

from . import constants as cont
from .finders.base_finder import BaseFinder
from .finders.point_collector import PointCollector
from .logs_and_errors import log_debug, raise_runtime_error


class FeatureFinder(BaseFinder):
    """A class to find different types of features in a vector layer."""

    def __init__(
        self, selected_layer: QgsVectorLayer, temp_point_layer: QgsVectorLayer
    ) -> None:
        """Initialize the FeatureFinder class.

        :param selected_layer: The QgsVectorLayer to search within.
        :param new_layer: The QgsVectorLayer to add new features to.
        """
        self.dim_field_name: str | None
        self.selected_layer_index: QgsSpatialIndex

        super().__init__(
            selected_layer=selected_layer,
            new_layer=temp_point_layer,
            selected_layer_index=self._create_spatial_index(selected_layer),
            dim_field_name=self._find_dim_field_name(selected_layer),
        )

    def _create_spatial_index(self, layer: QgsVectorLayer) -> QgsSpatialIndex:
        """Create a spatial index for the given layer."""
        log_debug(f"Creating spatial index for layer '{layer.name()}'.")
        request: QgsFeatureRequest = QgsFeatureRequest().setNoAttributes()
        index = QgsSpatialIndex(layer.getFeatures(request))
        log_debug("Spatial index created.", Qgis.Success)
        return index

    def _find_dim_field_name(self, layer: QgsVectorLayer) -> str | None:
        """Find the first matching dimension field name from the constants.

        Returns:
            The name of the found field, or None if no match is found.
        """
        layer_fields: QgsFields = layer.fields()
        found_name: str | None = next(
            (
                name
                for name in cont.Names.sel_layer_field_dim
                if layer_fields.lookupField(name) != -1
            ),
            None,
        )

        if found_name:
            log_debug(f"Found dimension field: '{found_name}'", Qgis.Success)
        else:
            log_debug("No dimension field found in the selected layer.", Qgis.Warning)
        return found_name

    def find_features(
        self,
        progress_bar: QProgressBar,
        pgb_update_text: Callable[[str], None],
    ) -> int:
        """Find and classify points of interest.

        Args:
            progress_bar: A QProgressBar to report progress.
            pgb_update_text: A function to update the progress bar's text.

        Returns:
            The total number of features created.
        """
        log_debug("Starting point-centric feature search.")

        if not self.new_layer.startEditing():
            raise_runtime_error("Failed to start editing the new layer.")

        # 1. Collect all points of interest
        pgb_update_text(
            QCoreApplication.translate("progress_bar", "Collecting points...")
        )
        collector = PointCollector(self.selected_layer, self.selected_layer_index)
        collected_points: dict[str, list[QgsPointXY]] = collector.collect_points(
            progress_bar
        )

        # 2. Directly classify all true intersections as "questionable"
        created_count: int = self._create_questionable_points(
            collected_points["intersections"]
        )

        # 3. Process the remaining vertices
        pgb_update_text(
            QCoreApplication.translate("progress_bar", "Analyzing points...")
        )
        progress_bar.setMaximum(len(collected_points["vertices"]))
        for i, point in enumerate(collected_points["vertices"]):
            created_count += self._process_point(point)
            progress_bar.setValue(i + 1)

        if not self.new_layer.commitChanges():
            raise_runtime_error("Failed to commit changes to the new layer.")

        log_debug("Feature search completed.", Qgis.Success)
        return created_count

    def _create_questionable_points(self, points: list[QgsPointXY]) -> int:
        """Create 'questionable' features for a list of points.

        Args:
            points: A list of QgsPointXY to be classified as questionable.

        Returns:
            The number of features created.
        """
        if not points:
            return 0

        log_debug(f"Creating {len(points)} questionable points for true intersections.")
        created_count = 0
        for point in points:
            search_geom = QgsGeometry.fromPointXY(point).buffer(
                cont.Numbers.search_radius, 5
            )
            features = self._get_intersecting_features(search_geom)
            attrs = {cont.NewLayerFields.type.name: cont.Names.attr_val_type_question}
            attrs |= self._get_connected_attributes(features)
            if self._create_feature(QgsGeometry.fromPointXY(point), attrs):
                created_count += 1
        return created_count

    def _process_point(self, point: QgsPointXY) -> int:
        """Analyze a single point and create the appropriate feature(s).

        Args:
            point: The point of interest to process.

        Returns:
            The number of features created for this point.
        """
        search_geom: QgsGeometry = QgsGeometry.fromPointXY(point).buffer(
            cont.Numbers.search_radius, 5
        )
        intersecting_features: list[QgsFeature] = self._get_intersecting_features(
            search_geom
        )
        n_intersections: int = len(intersecting_features)

        if n_intersections == 0:
            return 0  # Should not happen if points are from features

        # Case 1: A single line is involved.
        # This can be an endpoint or an intermediate vertex (a bend in multiline).
        if n_intersections == 1:
            if self._is_endpoint(point, intersecting_features[0]):
                return self._process_endpoint(point, intersecting_features[0])
            return self._process_bend(point, intersecting_features)

        # Case 2: Two lines intersect. This is always a bend candidate.
        if n_intersections < cont.Numbers.intersec_t:
            return self._process_bend(point, intersecting_features)

        # Case 3: Three (T-piece) or more (questionable) lines intersect.
        return self._process_t_piece_or_questionable(point, intersecting_features)

    def _process_bend(self, point: QgsPointXY, features: list[QgsFeature]) -> int:
        """Process a point where one or two lines meet, potentially forming a bend.

        This method handles bends within a single feature (an intermediate vertex)
        and bends formed by the intersection of two features.

        Args:
            point: The point of interest (intersection or vertex).
            features: A list containing one or two features.

        Returns:
            The number of features created (0 or 1).
        """
        p1, p3 = None, None
        if len(features) == 1:
            p1, p3 = self._get_adjacent_vertices(point, features[0])
        elif len(features) == 2:
            p1 = self._get_remote_point(features[0], point)
            p3 = self._get_remote_point(features[1], point)

        if not p1 or not p3:
            return 0  # Could not determine segments to calculate an angle

        angle = self._calculate_angle(p1, point, p3)

        if angle >= cont.Numbers.min_angle_bend:
            attrs = {
                cont.NewLayerFields.type.name: cont.Names.attr_val_type_bend,
                cont.NewLayerFields.angle.name: round(angle, 2),
            }
            attrs |= self._get_connected_attributes(features)
            if self._create_feature(QgsGeometry.fromPointXY(point), attrs):
                return 1
        return 0

    def _process_endpoint(self, point: QgsPointXY, feature: QgsFeature) -> int:
        """Process a point that is the endpoint of a single line."""
        # Check if it's a lone line segment or a true house connection
        is_other_end_connected = False
        for p in self._get_start_end_of_line(feature):
            if p.compare(point, cont.Numbers.tiny_number):
                continue  # This is the endpoint we are currently processing
            # Check if the *other* endpoint is connected to something
            other_end_search = QgsGeometry.fromPointXY(p).buffer(
                cont.Numbers.search_radius, 5
            )
            if len(self._get_intersecting_features(other_end_search)) > 1:
                is_other_end_connected = True
                break

        # If the other end is not connected, it's a floating line. Mark both ends.
        if not is_other_end_connected:
            count = 0
            for p_end in self._get_start_end_of_line(feature):
                attrs = {
                    cont.NewLayerFields.type.name: cont.Names.attr_val_type_question
                }
                attrs |= self._get_connected_attributes([feature])
                if self._create_feature(QgsGeometry.fromPointXY(p_end), attrs):
                    count += 1
            return count

        # Otherwise, it's a house connection
        attrs: dict[str, str] = {
            cont.NewLayerFields.type.name: cont.Names.attr_val_type_house
        }
        attrs |= self._get_connected_attributes([feature])
        if self._create_feature(QgsGeometry.fromPointXY(point), attrs):
            return 1
        return 0

    def _process_t_piece_or_questionable(
        self, point: QgsPointXY, features: list[QgsFeature]
    ) -> int:
        """Process a point where 3 or more lines meet."""
        n_intersections = len(features)

        # Check for poorly drawn lines nearby
        is_questionable = False
        for feature in features:
            for p in self._get_start_end_of_line(feature):
                distance = point.distance(p)
                # If an endpoint is very close but not AT the intersection point
                if 0 < distance < cont.Numbers.search_radius:
                    is_questionable = True
                    break
            if is_questionable:
                break

        if is_questionable or n_intersections > cont.Numbers.intersec_t:
            attrs: dict[str, str] = {
                cont.NewLayerFields.type.name: cont.Names.attr_val_type_question
            }
            attrs |= self._get_connected_attributes(features)
            if self._create_feature(QgsGeometry.fromPointXY(point), attrs):
                return 1
            return 0

        # It's a standard 3-way T-piece
        return self._create_t_piece_and_reducers(point, features)

    def _create_t_piece_and_reducers(
        self, point: QgsPointXY, features: list[QgsFeature]
    ) -> int:
        """Create a T-piece and any necessary reducers."""
        # This logic can be adapted from the old TPieceFinder
        # For simplicity in this refactoring, we'll just create the T-piece
        # and acknowledge that reducer logic would go here.

        num_t_pieces = len(features) - 2
        created_count = 0

        for i in range(num_t_pieces):
            t_piece_point = point
            if num_t_pieces > 1:
                # Small offset for multiple T-pieces from >3 intersections
                offset_dist = cont.Numbers.distance_t_reducer / 1.5
                angle = i * (2 * math.pi / num_t_pieces)
                offset_x = offset_dist * math.cos(angle)
                offset_y = offset_dist * math.sin(angle)
                t_piece_point = QgsPointXY(point.x() + offset_x, point.y() + offset_y)

            attrs = {cont.NewLayerFields.type.name: cont.Names.attr_val_type_t_piece}
            attrs |= self._get_connected_attributes(features)
            if self._create_feature(QgsGeometry.fromPointXY(t_piece_point), attrs):
                created_count += 1

        # TODO: Implement reducer creation logic here, similar to the old
        # TPieceFinder._create_t_piece_and_reducers and subsequent methods.
        # This would involve checking dimensions and creating reducer points.

        return created_count

    def _get_remote_point(
        self, feature: QgsFeature, intersection_point: QgsPointXY
    ) -> QgsPointXY | None:
        """For a feature and an intersection point on it, find the other endpoint
        of the segment that contains the intersection.
        """
        geom = feature.geometry()
        if not geom:
            return None

        # Find the vertex on the line segment closest to the intersection point
        _, _, after_vertex, _ = geom.closestSegmentWithContext(intersection_point)

        if after_vertex == 0:
            return None  # Should not happen if point is on the line

        p_before = QgsPointXY(geom.vertexAt(after_vertex - 1))
        p_after = QgsPointXY(geom.vertexAt(after_vertex))

        # Return the point of the segment that is NOT the intersection point
        if intersection_point.distance(p_before) < cont.Numbers.tiny_number:
            return p_after
        if intersection_point.distance(p_after) < cont.Numbers.tiny_number:
            return p_before

        # If intersection is in the middle of a segment, we need to decide which
        # end of the line is the "remote" one. We find the closest *endpoint* of
        # the entire line and return the *other* endpoint.
        start_p, end_p = self._get_start_end_of_line(feature)
        if start_p.distance(intersection_point) < end_p.distance(intersection_point):
            return end_p
        return start_p
