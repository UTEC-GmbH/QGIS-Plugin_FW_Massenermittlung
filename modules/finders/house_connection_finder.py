"""Module: house_connection_finder.py

This module contains the HouseConnectionFinder class.
"""

from typing import Callable

from qgis.core import QgsFeature, QgsGeometry, QgsPoint

from modules import constants as cont
from modules.logs_and_errors import log_debug

from .base_finder import BaseFinder


class HouseConnectionFinder(BaseFinder):
    """A class to find house connections."""

    def _is_questionable_point(self, point: QgsPoint, feature_id: int) -> bool:
        """Check if a point is questionable by looking for nearby poorly drawn lines."""
        # We look for the 2 nearest neighbors,
        # as the feature itself will be the closest.
        neighbor_ids: list[int] = self.selected_layer_index.nearestNeighbor(point, 2)

        # Remove the feature's own ID from the list of neighbors.
        if feature_id in neighbor_ids:
            neighbor_ids.remove(feature_id)

        if not neighbor_ids:
            return False

        # Get the closest neighbor feature
        closest_neighbor_id = neighbor_ids[0]
        if neighbor_feature := self.selected_layer.getFeature(closest_neighbor_id):
            # Calculate the distance to the neighbor's geometry
            distance = QgsGeometry.fromPointXY(point).distance(
                neighbor_feature.geometry()
            )

            # If the distance is within the search radius,
            # it's likely a poorly drawn line
            if distance < cont.Numbers.search_radius:
                return True

        return False

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
            for point in self._get_start_end_of_line(feature):
                intersecting_ids: list[int] = self._find_intersecting_feature_ids(
                    point, feature.id()
                )
                if intersecting_ids:
                    continue

                # Potential house connection found.
                is_poorly_drawn = self._is_questionable_point(
                    QgsPoint(point), feature.id()
                )

                attributes: dict[str, str]
                if is_poorly_drawn:
                    attributes = {
                        cont.NewLayerFields.type.name: cont.Names.attr_val_type_question
                    }
                else:
                    attributes = {
                        cont.NewLayerFields.type.name: cont.Names.attr_val_type_house
                    }

                attributes |= self._get_connected_attributes([feature])
                if self._create_feature(QgsGeometry.fromPointXY(point), attributes):
                    number_of_new_points += 1

            if progress_callback:
                progress_callback()

        log_debug(f"Checked {len(features)} intersections.")

        return number_of_new_points
