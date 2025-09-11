"""Module: find_stuff.py

This module contains the FeatureFinder class that finds things in the selected layer.
"""

from enum import Flag, auto

from qgis.core import Qgis, QgsFeature, QgsSpatialIndex, QgsVectorLayer
from qgis.PyQt.QtCore import (
    QCoreApplication,  # type: ignore[reportAttributeAccessIssue]
)

from .finders.bend_finder import BendFinder
from .finders.house_connection_finder import HouseConnectionFinder
from .finders.t_piece_finder import TPieceFinder
from .logs_and_errors import log_debug, raise_runtime_error


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
            raise_runtime_error(
                QCoreApplication.translate(
                    "RuntimeError", "Failed to start editing the new layer."
                )
            )

        if FeatureType.T_PIECES in feature_to_search:
            t_piece_finder = TPieceFinder(
                self.selected_layer, self.new_layer, self.selected_layer_index
            )
            found_counts[t_pieces] = t_piece_finder.find(self.selected_layer_features)

        if FeatureType.HOUSES in feature_to_search:
            house_connection_finder = HouseConnectionFinder(
                self.selected_layer, self.new_layer, self.selected_layer_index
            )
            found_counts[houses] = house_connection_finder.find(
                self.selected_layer_features
            )

        if FeatureType.BENDS in feature_to_search:
            bend_finder = BendFinder(
                self.selected_layer, self.new_layer, self.selected_layer_index
            )
            found_counts[bends] = bend_finder.find(self.selected_layer_features)

        if not self.new_layer.commitChanges():
            raise_runtime_error(
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
            raise_runtime_error(
                QCoreApplication.translate(
                    "RuntimeError", "No features found in the selected layer."
                )
            )
        log_debug(
            QCoreApplication.translate(
                "log", "Found {0} lines in the selected layer."
            ).format(len(features)),
            Qgis.Success,
        )
        return features
