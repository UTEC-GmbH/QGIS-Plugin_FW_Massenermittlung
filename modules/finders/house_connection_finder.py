"""Module: house_connection_finder.py

This module contains the HouseConnectionFinder class.
"""

from typing import Callable

from qgis.core import QgsFeature, QgsGeometry, QgsPoint, QgsPointXY

from modules import constants as cont
from modules.logs_and_errors import log_debug

from .base_finder import BaseFinder


class HouseConnectionFinder(BaseFinder):
    """A class to find house connections."""

    def _is_questionable_point(self, point: QgsPoint, feature_id: int) -> bool:
        """Check if a point is questionable by looking for nearby poorly drawn lines."""
        distance = self._nearest_neighbor_distance(QgsPointXY(point), feature_id)
        return bool(distance is not None and distance < cont.Numbers.search_radius)

    def _nearest_neighbor_distance(self, point: QgsPointXY, feature_id: int) -> float | None:
        """Return the distance from the given point to the nearest other feature (excluding the given feature)."""
        neighbor_ids: list[int] = self.selected_layer_index.nearestNeighbor(point, 2)
        if feature_id in neighbor_ids:
            neighbor_ids.remove(feature_id)
        if not neighbor_ids:
            return None
        neighbor_feature = self.selected_layer.getFeature(neighbor_ids[0])
        if neighbor_feature:
            return QgsGeometry.fromPointXY(point).distance(neighbor_feature.geometry())
        return None

    def find(
        self, features: list[QgsFeature], progress_callback: Callable | None = None
    ) -> int:
        """Find the endpoints of lines that are not connected to other lines.

        Args:
            features: A list of features to process.
            progress_callback: An optional function to call to report progress.

        Returns:
            The number of new points created.
        """
        number_of_new_points = 0
        for feature in features:
            # Collect all candidate endpoints for this feature (no intersections within search radius)
            candidate_points: list[tuple[QgsPointXY, float | None]] = []
            for point in self._get_start_end_of_line(feature):
                intersecting_ids: list[int] = self._find_intersecting_feature_ids(
                    point, feature.id()
                )
                if intersecting_ids:
                    continue

                distance = self._nearest_neighbor_distance(point, feature.id())
                candidate_points.append((point, distance))

            if len(candidate_points) == 1:
                point, _ = candidate_points[0]
                # Potential house connection found.
                is_poorly_drawn = self._is_questionable_point(
                    QgsPoint(point), feature.id()
                )

                attributes: dict[str, str]
                if is_poorly_drawn:
                    attributes = {cont.NewLayerFields.type.name: cont.Names.attr_val_type_question}
                else:
                    attributes = {cont.NewLayerFields.type.name: cont.Names.attr_val_type_house}

                attributes |= self._get_connected_attributes([feature])
                if self._create_feature(QgsGeometry.fromPointXY(point), attributes):
                    number_of_new_points += 1

            elif len(candidate_points) >= 2:
                # Enforce a single house connection per feature:
                # the endpoint farthest from any other feature is considered the true house connection,
                # all others become questionable points.
                def _norm_dist(d: float | None) -> float:
                    return d if d is not None else float("inf")

                # Find the index of the farthest candidate (largest distance -> best house connection)
                house_idx = max(range(len(candidate_points)), key=lambda i: _norm_dist(candidate_points[i][1]))

                for idx, (point, _) in enumerate(candidate_points):
                    if idx == house_idx:
                        type_value = cont.Names.attr_val_type_house
                    else:
                        type_value = cont.Names.attr_val_type_question

                    attributes = {cont.NewLayerFields.type.name: type_value}
                    attributes |= self._get_connected_attributes([feature])
                    if self._create_feature(QgsGeometry.fromPointXY(point), attributes):
                        number_of_new_points += 1

            if progress_callback:
                progress_callback()

        log_debug(f"Checked {len(features)} features for house connections.")

        return number_of_new_points
