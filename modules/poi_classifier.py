"""Module: find_stuff.py

This module contains the FeatureFinder class that finds things in the selected layer.
"""

from collections.abc import Callable

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QProgressBar

from . import constants as cont
from .logs_and_errors import log_debug, raise_runtime_error
from .point_collector import PointCollector
from .vector_analysis_tools import VectorAnalysisTools


class PointOfInterestClassifier(VectorAnalysisTools):
    """A class to find different types of features in a vector layer."""

    def __init__(
        self, selected_layer: QgsVectorLayer, temp_point_layer: QgsVectorLayer
    ) -> None:
        """Initialize the FeatureFinder class.

        Args:
            selected_layer: The QgsVectorLayer to search within.
            temp_point_layer: The QgsVectorLayer to add new features to.
        """
        super().__init__(selected_layer, temp_point_layer)

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
        log_debug(
            f"Creating {len(collected_points['intersections'])} "
            "questionable points for intersections without endpoints."
        )
        created_count: int = sum(
            self._create_questionable_point(
                point,
                note=QCoreApplication.translate(
                    "questionable_note", "Intersection without endpoints"
                ),
            )
            for point in collected_points["intersections"]
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
                return self._possible_house_connection(point, intersecting_features[0])
            return self._possible_bend(point, intersecting_features)

        # Case 2: Two lines intersect. This is always a bend candidate.
        if n_intersections < cont.Numbers.intersec_t:
            return self._possible_bend(point, intersecting_features)

        # Case 3: Three lines intersect. This is always a T-piece candidate.
        if n_intersections == cont.Numbers.intersec_t:
            return self._possible_t_piece(point, intersecting_features)

        # Case 4: More than three lines intersect. This is always a questionable point.
        return self._create_questionable_point(
            point,
            note=QCoreApplication.translate(
                "questionable_note", "More than three lines at intersection"
            ),
        )

    def _possible_bend(self, point: QgsPointXY, features: list[QgsFeature]) -> int:
        """Process a point where one or two lines meet, potentially forming a bend.

        This method handles bends within a single feature (an intermediate vertex)
        and bends formed by the intersection of two features.

        Args:
            point: The point of interest (intersection or vertex).
            features: A list containing one or two features.

        Returns:
            The number of features created (0 or 1).
        """
        p1: QgsPointXY | None = None
        p3: QgsPointXY | None = None
        if len(features) == 1:
            p1, p3 = self._get_adjacent_vertices(point, features[0])
        elif len(features) == 2:  # noqa: PLR2004
            p1 = self._get_other_endpoint(features[0], point)
            p3 = self._get_other_endpoint(features[1], point)

        if not p1 or not p3:
            return 0  # Could not determine segments to calculate an angle

        angle: float = self._calculate_angle(p1, point, p3)
        return self._create_bend(point, features, angle)

    def _possible_house_connection(self, point: QgsPointXY, feature: QgsFeature) -> int:
        """Process a point that is the endpoint of a single line."""
        # Check if it's a lone line segment or a true house connection
        is_other_end_connected = False
        for s_e_point in self._get_start_end_of_line(feature):
            if s_e_point.compare(point, cont.Numbers.tiny_number):
                continue  # This is the endpoint we are currently processing
            # Check if the *other* endpoint is connected to something
            other_end_search: QgsGeometry = QgsGeometry.fromPointXY(s_e_point).buffer(
                cont.Numbers.search_radius, 5
            )
            if len(self._get_intersecting_features(other_end_search)) > 1:
                is_other_end_connected = True
                break

        # If the other end is not connected, it's a floating line. Mark both ends.
        if not is_other_end_connected:
            return sum(
                self._create_questionable_point(
                    p_end,
                    [feature],
                    note=QCoreApplication.translate(
                        "questionable_note", "Unconnected line"
                    ),
                )
                for p_end in self._get_start_end_of_line(feature)
            )

        return self._create_house_connection(point, [feature])

    def _possible_t_piece(self, point: QgsPointXY, features: list[QgsFeature]) -> int:
        """Process a point where 3 lines meet."""

        # Check for poorly drawn lines nearby
        for feature in features:
            for p in self._get_start_end_of_line(feature):
                distance: float = point.distance(p)
                # If an endpoint is very close but not AT the intersection point
                if 0 < distance < cont.Numbers.search_radius:
                    return self._create_questionable_point(
                        point,
                        features,
                        note=QCoreApplication.translate(
                            "questionable_note", "Endpoint near intersection"
                        ),
                    )

        return self._create_t_piece(point, features)

    def _create_questionable_point(
        self,
        point: QgsPointXY,
        features: list[QgsFeature] | None = None,
        note: str | None = None,
    ) -> int:
        """Create a 'questionable' point feature.

        Args:
            point: The location of the point.
            features: Connected features. If None, they are found by searching.
            note: An optional note to add to the feature's attributes.

        Returns:
            1 if the feature was created successfully, 0 otherwise.
        """
        if features is None:
            search_geom: QgsGeometry = QgsGeometry.fromPointXY(point).buffer(
                cont.Numbers.search_radius, 5
            )
            features = self._get_intersecting_features(search_geom)

        attrs: dict[str, str | None] = {
            cont.NewLayerFields.type.name: cont.Names.attr_val_type_question
        }
        attrs |= self._get_connected_attributes(features)
        if note:
            attrs[cont.NewLayerFields.notes.name] = note
        return 1 if self._create_feature(QgsGeometry.fromPointXY(point), attrs) else 0

    def _create_bend(
        self, point: QgsPointXY, features: list[QgsFeature], angle: float
    ) -> int:
        """Create a 'bend' feature if the angle is sufficient.

        Args:
            point: The location of the bend.
            features: The list of connected features.
            angle: The calculated angle of the bend.

        Returns:
            1 if the feature was created successfully, 0 otherwise.
        """
        if angle < cont.Numbers.min_angle_bend:
            return 0

        attrs: dict = {
            cont.NewLayerFields.type.name: cont.Names.attr_val_type_bend,
            cont.NewLayerFields.angle.name: round(angle, 2),
        }
        attrs |= self._get_connected_attributes(features)
        return 1 if self._create_feature(QgsGeometry.fromPointXY(point), attrs) else 0

    def _create_house_connection(
        self, point: QgsPointXY, features: list[QgsFeature]
    ) -> int:
        """Create a 'house connection' feature.

        Args:
            point: The location of the house connection.
            features: The list of connected features (should be one).

        Returns:
            1 if the feature was created successfully, 0 otherwise.
        """
        attrs: dict = {cont.NewLayerFields.type.name: cont.Names.attr_val_type_house}
        attrs |= self._get_connected_attributes(features)
        return 1 if self._create_feature(QgsGeometry.fromPointXY(point), attrs) else 0

    def _create_t_piece(self, point: QgsPointXY, features: list[QgsFeature]) -> int:
        """Create a 'T-piece' feature.

        Args:
            point: The location of the T-piece.
            features: The list of connected features.

        Returns:
            1 if the feature was created successfully, 0 otherwise.
        """
        attrs: dict = {cont.NewLayerFields.type.name: cont.Names.attr_val_type_t_piece}
        attrs |= self._get_connected_attributes(features)
        return 1 if self._create_feature(QgsGeometry.fromPointXY(point), attrs) else 0
