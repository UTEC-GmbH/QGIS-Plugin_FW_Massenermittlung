"""Module: t_intersection_analyzer.py

This module contains the TIntersectionAnalyzer class.
"""

from qgis.core import (
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import constants as cont
from .vector_analysis_tools import VectorAnalysisTools


class TIntersectionAnalyzer(VectorAnalysisTools):
    """A class to classify T-pieces and associated features."""

    def process_t_intersection(
        self, point: QgsPointXY, features: list[QgsFeature]
    ) -> int:
        """Analyzes a 3-way intersection and creates appropriate features.

        This method identifies the main and connecting pipes, checks for bends
        and dimension changes, and creates T-pieces, bends, and reducers
        as needed.

        Args:
            point: The intersection point.
            features: The three features intersecting at the point.

        Returns:
            The number of features created.
        """
        created_count: int = 0

        # 1. Find the main pipe (the two most collinear lines)
        main_pipe_features, connecting_pipe = self._find_main_pipe(point, features)
        if not main_pipe_features or not connecting_pipe:
            return self.create_questionable_point(
                point,
                features,
                note=QCoreApplication.translate(
                    "feature_note", "Could not determine main pipe."
                ),
            )

        # 2. Get the remote endpoints of the main pipe
        p_main_1: QgsPointXY | None = self.get_other_endpoint(
            main_pipe_features[0], point
        )
        p_main_2: QgsPointXY | None = self.get_other_endpoint(
            main_pipe_features[1], point
        )

        if not p_main_1 or not p_main_2:
            return self.create_questionable_point(
                point,
                features,
                note=QCoreApplication.translate(
                    "feature_note", "Could not determine main pipe endpoints."
                ),
            )

        # 3. Check for a bend in the main pipe. The logic depends on this.
        bend_angle: float = self.calculate_angle(p_main_1, point, p_main_2)
        if bend_angle < (cont.Numbers.circle_semi - cont.Numbers.min_angle_bend):
            # If there's a bend, the bend is at the intersection point.
            created_count += self.create_bend(point, main_pipe_features, bend_angle)

            # The T-piece is offset along the main pipe.
            # We'll place it on the segment with the larger diameter.
            if self.dim_field_name and main_pipe_features[0].attribute(
                self.dim_field_name
            ) < main_pipe_features[1].attribute(self.dim_field_name):
                target_feature = main_pipe_features[1]
            else:
                target_feature = main_pipe_features[0]

            t_point = self._get_point_along_line(
                point, target_feature, cont.Numbers.distance_t_bend
            )
            t_point = t_point or point  # Fallback to original point

        else:
            # If there's no bend, the T-piece is at the intersection point.
            t_point = point

        # Build the note with main pipe IDs and dimensions
        note_parts: list[str] = []
        for feature in main_pipe_features:
            part: str = str(feature.attribute("original_fid"))
            if self.dim_field_name and (dim := feature.attribute(self.dim_field_name)):
                part += f" ({cont.Names.dim_prefix}{dim})"
            note_parts.append(part)

        note: str = QCoreApplication.translate("feature_note", "Main pipe: {0}").format(
            " & ".join(note_parts)
        )

        created_count += self._create_t_piece_with_correct_dims(
            t_point, main_pipe_features, connecting_pipe, note
        )

        # 4. Check if a reducer on the main pipe is needed
        if self.dim_field_name:
            created_count += self._check_and_create_reducer(
                point, main_pipe_features, connecting_pipe
            )

        return created_count

    def _find_main_pipe(
        self, point: QgsPointXY, features: list[QgsFeature]
    ) -> tuple[list[QgsFeature], QgsFeature | None]:
        """Identify the main pipe and connecting pipe from three features.

        The main pipe is the pair of features that are most collinear.

        Args:
            point: The intersection point.
            features: A list of three intersecting features.

        Returns:
            A tuple containing (list of 2 main pipe features, connecting pipe feature).
            Returns ([], None) if identification fails.
        """
        if len(features) != cont.Numbers.intersec_t:
            return [], None

        # If exactly one of the three lines has a free endpoint (a house connection),
        # it's the connecting pipe.
        house_conn_features: list[QgsFeature] = []
        for feature in features:
            other_end: QgsPointXY | None = self.get_other_endpoint(feature, point)
            if not other_end:
                continue

            search_geom: QgsGeometry = QgsGeometry.fromPointXY(other_end).buffer(
                cont.Numbers.search_radius, 5
            )
            # If only one feature intersects (the line itself), it's a free end.
            if len(self.get_intersecting_features(search_geom)) == 1:
                house_conn_features.append(feature)

        if len(house_conn_features) == 1:
            connecting_pipe = house_conn_features[0]
            main_pipe_pair = [f for f in features if f != connecting_pipe]
            return main_pipe_pair, connecting_pipe

        # --- Fallback to original angle-based logic ---
        feature_endpoints: dict[int, QgsPointXY | None] = {
            f.id(): self.get_other_endpoint(f, point) for f in features
        }

        max_angle: float = -1.0
        main_pipe_pair: list[QgsFeature] = []

        # Iterate through all pairs of features to find the most collinear pair
        for i in range(cont.Numbers.intersec_t):
            for j in range(i + 1, cont.Numbers.intersec_t):
                f1, f2 = features[i], features[j]
                p1, p2 = feature_endpoints[f1.id()], feature_endpoints[f2.id()]

                if p1 and p2:
                    angle = self.calculate_angle(p1, point, p2)
                    # The most collinear pair will have the largest angle
                    if angle > max_angle:
                        max_angle = angle
                        main_pipe_pair = [f1, f2]

        if not main_pipe_pair:
            return [], None

        # The remaining feature is the connecting pipe
        connecting_pipe: QgsFeature | None = next(
            (f for f in features if f not in main_pipe_pair), None
        )
        return main_pipe_pair, connecting_pipe

    def _create_t_piece_with_correct_dims(
        self,
        point: QgsPointXY,
        main_pipe: list[QgsFeature],
        connecting_pipe: QgsFeature,
        note: str,
    ) -> int:
        """Create a T-piece with correctly derived dimensions.

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
                t_dims: list[int] = [main_dims[-1], conn_dim]
                dims_str: str = cont.Names.dim_separator.join(
                    f"{cont.Names.dim_prefix}{d}" for d in sorted(t_dims, reverse=True)
                )
                attrs[cont.NewLayerFields.dimensions.name] = dims_str

        return 1 if self.create_feature(QgsGeometry.fromPointXY(point), attrs) else 0

    def _check_and_create_reducer(
        self,
        point: QgsPointXY,
        main_pipe: list[QgsFeature],
        connecting_pipe: QgsFeature,
    ) -> int:
        """Check for dimension changes and creates a reducer if necessary.

        If the dimension jump is larger than `max_dim_jump_reducer`, this method
        creates multiple reducers to bridge the gap. Each reducer's `dimensions`
        attribute will show the 'from' and 'to' dimensions (e.g., 'DN25/DN20').

        Args:
            point: The intersection point.
            main_pipe: The two features forming the main pipe.
            connecting_pipe: The feature forming the connecting pipe.

        Returns:
            The number of reducer features created (0 or more).
        """
        if not self.dim_field_name:
            return 0

        dim_main_1 = main_pipe[0].attribute(self.dim_field_name)
        dim_main_2 = main_pipe[1].attribute(self.dim_field_name)
        dim_conn = connecting_pipe.attribute(self.dim_field_name)

        # Ensure dimensions are valid numbers before proceeding
        if not all(isinstance(d, (int, float)) for d in [dim_main_1, dim_main_2]):
            return 0

        # Scenario: Main pipe has a dimension change
        if dim_main_1 != dim_main_2:
            large_dim = max(dim_main_1, dim_main_2)
            small_dim = min(dim_main_1, dim_main_2)
            smaller_dim_feature = (
                main_pipe[0] if dim_main_1 < dim_main_2 else main_pipe[1]
            )

            try:
                large_idx: int = cont.PipeDimensions.diameters.index(large_dim)
                small_idx: int = cont.PipeDimensions.diameters.index(small_dim)
            except ValueError:
                # One of the dimensions is not a standard pipe size
                return self.create_questionable_point(
                    point,
                    main_pipe,
                    note=QCoreApplication.translate(
                        "feature_note",
                        "Non-standard pipe dimension detected for reducer.",
                    ),
                )

            dim_steps = large_idx - small_idx
            if dim_steps <= 0:
                return 0  # Should not happen if dims are different

            num_reducers = (
                dim_steps - 1
            ) // cont.PipeDimensions.max_dim_jump_reducer + 1
            created_count = 0

            for i in range(num_reducers):
                current_large_idx = (
                    large_idx - i * cont.PipeDimensions.max_dim_jump_reducer
                )
                current_small_idx = max(
                    small_idx,
                    large_idx - (i + 1) * cont.PipeDimensions.max_dim_jump_reducer,
                )

                dim_from: str = (
                    f"{cont.Names.dim_prefix}"
                    f"{cont.PipeDimensions.diameters[current_large_idx]}"
                )
                dim_to: str = (
                    f"{cont.Names.dim_prefix}"
                    f"{cont.PipeDimensions.diameters[current_small_idx]}"
                )

                # Place reducers along the smaller pipe segment
                distance: float = cont.Numbers.distance_t_reducer * (i + 1)
                if reducer_point := self._get_point_along_line(
                    point, smaller_dim_feature, distance
                ):
                    dims_str: str = f"{dim_from}{cont.Names.dim_separator}{dim_to}"
                    # Get base attributes first, then overwrite the dimensions.
                    reducer_attrs: dict = self.get_connected_attributes(
                        [smaller_dim_feature]
                    )
                    reducer_attrs[cont.NewLayerFields.type.name] = (
                        cont.Names.attr_val_type_reducer
                    )
                    reducer_attrs[cont.NewLayerFields.dimensions.name] = dims_str
                    if self.create_feature(
                        QgsGeometry.fromPointXY(reducer_point), reducer_attrs
                    ):
                        created_count += 1

            return created_count

        if dim_conn is not None and dim_main_1 is not None and dim_conn > dim_main_1:
            return self.create_questionable_point(
                point,
                [*main_pipe, connecting_pipe],
                note=QCoreApplication.translate(
                    "feature_note",
                    "Connecting pipe has a larger diameter than the main pipe.",
                ),
            )
        return 0

    def _get_point_along_line(
        self, start_point: QgsPointXY, feature: QgsFeature, distance: float
    ) -> QgsPointXY | None:
        """Get a point at a specific distance from the start point along a feature."""
        other_endpoint = self.get_other_endpoint(feature, start_point)
        if not other_endpoint:
            return None

        azimuth = start_point.azimuth(other_endpoint)
        return start_point.project(distance, azimuth)
