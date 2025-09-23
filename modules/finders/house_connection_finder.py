"""Module: house_connection_finder.py

This module contains the HouseConnectionFinder class.
"""

from typing import Callable

from qgis.core import QgsFeature, QgsGeometry

from modules import constants as cont
from modules.logs_and_errors import log_debug

from .base_finder import BaseFinder


class HouseConnectionFinder(BaseFinder):
    """A class to find house connections."""

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
                if not intersecting_ids:
                    attributes: dict[str, str] = {
                        cont.NewLayerFields.type.name: cont.Names.attr_val_type_house
                    }
                    attributes |= self._get_connected_attributes([feature])
                    if self._create_feature(QgsGeometry.fromPointXY(point), attributes):
                        number_of_new_points += 1

            if progress_callback:
                progress_callback()

        log_debug(f"Checked {len(features)} intersections.")

        return number_of_new_points
