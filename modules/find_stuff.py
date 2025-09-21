"""Module: find_stuff.py

This module contains the FeatureFinder class that finds things in the selected layer.
"""

from enum import Flag, auto

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsFeatureRequest,
    QgsSpatialIndex,
    QgsVectorLayer,
)
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
        log_debug("Initializing FeatureFinder...")
        log_debug(
            f"FeatureFinder received layer with feature count: "
            f"{selected_layer.featureCount()}",
            Qgis.Info,
        )
        self.selected_layer: QgsVectorLayer = selected_layer

        request = QgsFeatureRequest()
        request.setNoAttributes()
        self.selected_layer_index: QgsSpatialIndex = QgsSpatialIndex(
            self.selected_layer.getFeatures(request)
        )
        log_debug("Spatial index created for selected layer.")

        self.selected_layer_features: list[QgsFeature] = self._get_all_features()

        self.new_layer: QgsVectorLayer = new_layer
        log_debug("FeatureFinder initialized successfully.", Qgis.Success)

    def find_features(self, feature_to_search: FeatureType) -> dict[str, int]:
        """Find features based on the provided flags.

        :param feature_types: A flag combination of the features to find.
        :returns: A dictionary with the count of found features.
        """
        log_debug(f"Starting feature search for: {feature_to_search}")
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
            log_debug("Searching for T-pieces...")
            t_piece_finder = TPieceFinder(
                self.selected_layer, self.new_layer, self.selected_layer_index
            )
            found_counts[t_pieces] = t_piece_finder.find(self.selected_layer_features)
            log_debug(f"Found {found_counts[t_pieces]} T-pieces.")

        if FeatureType.HOUSES in feature_to_search:
            log_debug("Searching for house connections...")
            house_connection_finder = HouseConnectionFinder(
                self.selected_layer, self.new_layer, self.selected_layer_index
            )
            found_counts[houses] = house_connection_finder.find(
                self.selected_layer_features
            )
            log_debug(f"Found {found_counts[houses]} house connections.")

        if FeatureType.BENDS in feature_to_search:
            log_debug("Searching for bends...")
            bend_finder = BendFinder(
                self.selected_layer, self.new_layer, self.selected_layer_index
            )
            found_counts[bends] = bend_finder.find(self.selected_layer_features)
            log_debug(f"Found {found_counts[bends]} bends.")

        if not self.new_layer.commitChanges():
            raise_runtime_error(
                QCoreApplication.translate(
                    "RuntimeError", "Failed to commit changes to the new layer."
                )
            )

        log_debug("Feature search completed.", Qgis.Success)
        return found_counts

    def _get_all_features(self) -> list[QgsFeature]:
        """Get all features from the selected layer."""
        log_debug("Getting all features from the selected layer...")

        log_debug(
            f"Getting all features. "
            f"Layer feature count: {self.selected_layer.featureCount()}"
        )

        all_ids = list(self.selected_layer.allFeatureIds())
        log_debug(f"Found {len(all_ids)} feature IDs.")

        features: list[QgsFeature] = []
        for fid in all_ids:
            try:
                feature = self.selected_layer.getFeature(fid)
                features.append(feature)
            except Exception as e:
                log_debug(f"Could not fetch feature with ID {fid}: {e!s}", Qgis.Warning)

        if not features:
            raise_runtime_error(
                QCoreApplication.translate(
                    "RuntimeError",
                    "No features could be successfully fetched "
                    "from the selected layer.",
                )
            )
        log_debug(f"Successfully fetched {len(features)} features.", Qgis.Success)
        return features
