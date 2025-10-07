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
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QProgressBar

from . import constants as cont
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
        self, selected_layer: QgsVectorLayer, temp_point_layer: QgsVectorLayer
    ) -> None:
        """Initialize the FeatureFinder class.

        :param selected_layer: The QgsVectorLayer to search within.
        :param new_layer: The QgsVectorLayer to add new features to.
        """
        log_debug("Initializing FeatureFinder...")
        log_debug(
            f"FeatureFinder received selected (in-memory) layer "
            f"'{selected_layer.name()}' (feature count: "
            f"{selected_layer.featureCount()}, field count: "
            f"{len(selected_layer.fields())}), and a tempoprary "
            f"point layer (feature count: {temp_point_layer.featureCount()}, "
            f"field count: {len(temp_point_layer.fields())})."
        )
        self.selected_layer: QgsVectorLayer = selected_layer

        request = QgsFeatureRequest()
        request.setNoAttributes()
        self.selected_layer_index: QgsSpatialIndex = QgsSpatialIndex(
            self.selected_layer.getFeatures(request)
        )
        log_debug("Spatial index created for selected layer.")

        self.selected_layer_features: list[QgsFeature] = self._get_all_features()

        self.new_layer: QgsVectorLayer = temp_point_layer
        log_debug("FeatureFinder initialized successfully.", Qgis.Success)

    def find_features(
        self, feature_to_search: FeatureType, progress_bar: QProgressBar
    ) -> dict[str, int]:
        """Find features based on the provided flags.

        Args:
            feature_to_search: A flag combination of the features to find.
            progress_bar: A QProgressBar to report progress.

        Returns:
            A dictionary with the count of found features.
        """
        log_debug("Starting feature search.")
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
        # --- Calculate total steps for progress bar ---
        num_features = len(self.selected_layer_features)
        num_finders = 0
        if FeatureType.T_PIECES in feature_to_search:
            num_finders += 1
        if FeatureType.HOUSES in feature_to_search:
            num_finders += 1
        if FeatureType.BENDS in feature_to_search:
            num_finders += 1

        total_steps: int = num_features * num_finders
        progress_bar.setMaximum(total_steps)
        current_step = 0

        def progress_callback() -> None:
            nonlocal current_step
            current_step += 1
            progress_bar.setValue(current_step)

        if not self.new_layer.startEditing():
            raise_runtime_error("Failed to start editing the new layer.")

        if FeatureType.T_PIECES in feature_to_search:
            log_debug("Searching for T-pieces...")
            t_piece_finder = TPieceFinder(
                self.selected_layer, self.new_layer, self.selected_layer_index
            )
            found_counts[t_pieces] = t_piece_finder.find(
                self.selected_layer_features, progress_callback
            )
            log_debug(f"Found {found_counts[t_pieces]} T-pieces.")

        if FeatureType.HOUSES in feature_to_search:
            log_debug("Searching for house connections...")
            house_connection_finder = HouseConnectionFinder(
                self.selected_layer, self.new_layer, self.selected_layer_index
            )
            found_counts[houses] = house_connection_finder.find(
                self.selected_layer_features, progress_callback
            )
            log_debug(f"Found {found_counts[houses]} house connections.")

        if FeatureType.BENDS in feature_to_search:
            log_debug("Searching for bends...")
            bend_finder = BendFinder(
                self.selected_layer, self.new_layer, self.selected_layer_index
            )
            found_counts[bends] = bend_finder.find(
                self.selected_layer_features, progress_callback
            )
            log_debug(f"Found {found_counts[bends]} bends.")

        if not self.new_layer.commitChanges():
            raise_runtime_error("Failed to commit changes to the new layer.")

        log_debug("Feature search completed.", Qgis.Success)
        return found_counts

    def _get_all_features(self) -> list[QgsFeature]:
        """Get all features from the selected layer."""
        log_debug("Getting all features from the selected layer...")

        request = QgsFeatureRequest()
        # Only load the 'diameter' field, and the geometry
        dim_field_index = self.selected_layer.fields().lookupField(
            cont.Names.sel_layer_field_dim
        )
        if dim_field_index == -1:
            raise_runtime_error(
                f"Field '{cont.Names.sel_layer_field_dim}' not found in selected layer."
            )
        request.setSubsetOfAttributes([dim_field_index])
        request.setFlags(QgsFeatureRequest.NoGeometry)

        features: list[QgsFeature] = []
        features.extend(iter(self.selected_layer.getFeatures(request)))

        if not features:
            raise_runtime_error(
                "No features could be successfully fetched from the selected layer."
            )
        log_debug(
            f"Successfully fetched {len(features)} features from the selected layer.",
            Qgis.Success,
        )

        return features
