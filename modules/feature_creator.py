"""Module: feature_creator.py

This module contains the FeatureCreator class for creating QgsFeature objects.
"""

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import constants as cont
from .logs_and_errors import log_debug
from .vector_analysis_tools import VectorAnalysisTools


class FeatureCreator(VectorAnalysisTools):
    """A class to create specific types of point features."""

    def __init__(
        self,
        selected_layer: QgsVectorLayer,
        temp_point_layer: QgsVectorLayer,
    ) -> None:
        """Initialize the FeatureCreator.

        Args:
            selected_layer: The QgsVectorLayer being analyzed.
            temp_point_layer: The temporary QgsVectorLayer to add new features to.
        """
        super().__init__(selected_layer, temp_point_layer)

    def create_questionable_point(
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
            features = self.get_intersecting_features(search_geom)

        if not features:
            log_debug(
                f"Could not create questionable point at {point.asWkt()}: "
                "No features found.",
                Qgis.Warning,
            )
            return 0

        attrs: dict[str, str | None] = {
            cont.NewLayerFields.type.name: cont.Names.attr_val_type_question
        }
        attrs |= self.get_connected_attributes(features)
        if note:
            attrs[cont.NewLayerFields.notes.name] = note
        return 1 if self.create_feature(QgsGeometry.fromPointXY(point), attrs) else 0

    def create_house_connection(
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
        attrs |= self.get_connected_attributes(features)
        return 1 if self.create_feature(QgsGeometry.fromPointXY(point), attrs) else 0

    def create_bend(
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
        if angle > (cont.Numbers.circle_semi - cont.Numbers.min_angle_bend):
            return 0

        attrs: dict = {
            cont.NewLayerFields.type.name: cont.Names.attr_val_type_bend,
            cont.NewLayerFields.angle.name: round(cont.Numbers.circle_semi - angle, 2),
        }
        attrs |= self.get_connected_attributes(features)
        return 1 if self.create_feature(QgsGeometry.fromPointXY(point), attrs) else 0

    def create_t_piece(
        self,
        point: QgsPointXY,
        main_pipe: list[QgsFeature],
        connecting_pipe: QgsFeature,
        note: str,
    ) -> int:
        """Create a T-piece.

        The T-piece dimension is determined by the largest dimension of the main
        pipe and the dimension of the connecting pipe.

        Args:
            point: The geometry point for the T-piece.
            main_pipe: A list of the two features forming the main pipe.
            connecting_pipe: The feature for the connecting pipe.
            note: A note to add to the feature's attributes.

        Returns:
            1 if the feature was created successfully, 0 otherwise.
        """
        all_features: list[QgsFeature] = [*main_pipe, connecting_pipe]
        attrs: dict = {
            cont.NewLayerFields.type.name: cont.Names.attr_val_type_t_piece,
            cont.NewLayerFields.notes.name: note,
        }
        attrs |= self.get_connected_attributes(all_features)

        if self.dim_field_name:
            main_dims: list[int] = sorted(
                [
                    f.attribute(self.dim_field_name)
                    for f in main_pipe
                    if f.attribute(self.dim_field_name) is not None
                ]
            )
            conn_dim: int | None = connecting_pipe.attribute(self.dim_field_name)

            if main_dims and conn_dim is not None:
                # T-piece uses the largest main pipe dim and the connecting pipe dim
                t_dims_str: list[str] = [
                    f"{cont.Names.dim_prefix}{main_dims[-1]}",
                    f"{cont.Names.dim_prefix}{conn_dim}",
                ]
                dims_str: str = cont.Names.dim_separator.join(
                    sorted(t_dims_str, reverse=True)
                )
                attrs[cont.NewLayerFields.dimensions.name] = dims_str

        return 1 if self.create_feature(QgsGeometry.fromPointXY(point), attrs) else 0

    def create_reducers(
        self,
        point: QgsPointXY,
        dim_main_1: float,
        dim_main_2: float,
        main_pipe: list[QgsFeature],
        distance: float = cont.Numbers.distance_t_reducer,
    ) -> int:
        """Create reducers for a dimension change in the main pipe.

        This method calculates how many reducers are needed and creates them
        at appropriate distances from the intersection point.

        Args:
            point: The intersection point.
            dim_main_1: Dimension of the first main pipe feature.
            dim_main_2: Dimension of the second main pipe feature.
            main_pipe: The two features forming the main pipe.
            distance: The distance between the intersection and the first reducer.

        Returns:
            The number of reducer features created.
        """
        large_dim: float = max(dim_main_1, dim_main_2)
        small_dim: float = min(dim_main_1, dim_main_2)
        smaller_dim_feature: QgsFeature = (
            main_pipe[0] if dim_main_1 < dim_main_2 else main_pipe[1]
        )
        pref: str = cont.Names.dim_prefix

        try:
            large_idx: int = cont.PipeDimensions.diameters.index(large_dim)
            small_idx: int = cont.PipeDimensions.diameters.index(small_dim)
        except ValueError:
            # fmt: off
            note_text: str = QCoreApplication.translate("feature_note", "Non-standard pipe dimension detected for reducer.")  # noqa: E501
            # fmt: on
            return self.create_questionable_point(point, main_pipe, note=note_text)

        dim_steps: int = large_idx - small_idx
        if dim_steps <= 0:
            return 0

        num_reducers: int = (
            dim_steps - 1
        ) // cont.PipeDimensions.max_dim_jump_reducer + 1
        created_count = 0

        for i in range(num_reducers):
            distance += cont.Numbers.distance_t_reducer * i
            reducer_point: QgsPointXY | None = self.get_point_along_line(
                point, smaller_dim_feature, distance
            )
            if not reducer_point:
                continue

            current_large_idx: int = (
                large_idx - i * cont.PipeDimensions.max_dim_jump_reducer
            )
            current_small_idx: int = max(
                small_idx,
                large_idx - (i + 1) * cont.PipeDimensions.max_dim_jump_reducer,
            )
            dim_from: str = f"{pref}{cont.PipeDimensions.diameters[current_large_idx]}"
            dim_to: str = f"{pref}{cont.PipeDimensions.diameters[current_small_idx]}"
            dims_str: str = cont.Names.dim_separator.join([dim_from, dim_to])
            reducer_attrs: dict = self.get_connected_attributes([smaller_dim_feature])
            reducer_attrs |= {
                cont.NewLayerFields.type.name: cont.Names.attr_val_type_reducer,
                cont.NewLayerFields.dimensions.name: dims_str,
            }
            created_count += self.create_feature(
                QgsGeometry.fromPointXY(reducer_point), reducer_attrs
            )

        return created_count
