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
            # fmt: off
            note_text:str = QCoreApplication.translate("feature_note", "Could not determine main pipe.")  # noqa: E501
            # fmt: on
            return self.create_questionable_point(point, features, note=note_text)

        # 2. Get the remote endpoints of the main pipe
        p_main_1: QgsPointXY | None = self.get_other_endpoint(
            main_pipe_features[0], point
        )
        p_main_2: QgsPointXY | None = self.get_other_endpoint(
            main_pipe_features[1], point
        )

        if not p_main_1 or not p_main_2:
            # fmt: off
            note_text:str = QCoreApplication.translate("feature_note", "Could not determine main pipe endpoints.")  # noqa: E501
            # fmt: on
            return self.create_questionable_point(point, features, note=note_text)

        # 3. Check for a bend in the main pipe. The logic depends on this.
        bend_angle: float = self.calculate_angle(p_main_1, point, p_main_2)
        t_point: QgsPointXY = point

        if bend_angle < (cont.Numbers.circle_semi - cont.Numbers.min_angle_bend):
            # If there's a significant bend in the main pipe, create a bend feature
            # at the intersection point. The T-piece will also be at this point.
            created_count += self.create_bend(point, main_pipe_features, bend_angle)

        # Build the note with main pipe IDs and dimensions
        note_parts: list[str] = []
        for feature in main_pipe_features:
            part: str = str(feature.attribute("original_fid"))
            if self.dim_field_name and (dim := feature.attribute(self.dim_field_name)):
                part += f" ({cont.Names.dim_prefix}{dim})"
            note_parts.append(part)

        # fmt: off
        note_text: str = QCoreApplication.translate("feature_note", "Main pipe: {0}").format(" & ".join(note_parts))  # noqa: E501
        # fmt: on
        created_count += self._create_t_piece(
            t_point, main_pipe_features, connecting_pipe, note_text
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

        This method first attempts to identify the connecting pipe by checking for a
        feature with a free endpoint (a house connection). If that fails, it falls
        back to finding the two most collinear features, which are assumed to form
        the main pipe.

        Args:
            point: The intersection point.
            features: A list of three intersecting features.

        Returns:
            A tuple containing a list of the two main pipe features and the single
            connecting pipe feature. Returns ([], None) if identification fails.
        """
        if len(features) != cont.Numbers.intersec_t:
            return [], None

        # Strategy 1: Check for a single, unconnected endpoint (house connection)
        main_pipe, conn_pipe = self._find_pipe_by_endpoint_connectivity(point, features)
        if main_pipe and conn_pipe:
            return main_pipe, conn_pipe

        # Strategy 2: Fallback to finding the most collinear pair by angle
        return self._find_pipe_by_angle(point, features)

    def _find_pipe_by_endpoint_connectivity(
        self, point: QgsPointXY, features: list[QgsFeature]
    ) -> tuple[list[QgsFeature] | None, QgsFeature | None]:
        """Identify pipes by checking for a feature with a free endpoint.

        If exactly one of the three features has an endpoint that is not connected
        to any other line, that feature is considered the connecting pipe.

        Args:
            point: The intersection point.
            features: A list of three intersecting features.

        Returns:
            A tuple of (main_pipe_features, connecting_pipe_feature) if successful,
            otherwise (None, None).
        """
        unconnected_features: list[QgsFeature] = []
        for feature in features:
            other_end: QgsPointXY | None = self.get_other_endpoint(feature, point)
            if not other_end:
                continue

            search_geom: QgsGeometry = QgsGeometry.fromPointXY(other_end).buffer(
                cont.Numbers.search_radius, 5
            )
            # A free end intersects with only one feature: the line itself.
            if len(self.get_intersecting_features(search_geom)) == 1:
                unconnected_features.append(feature)

        if len(unconnected_features) == 1:
            connecting_pipe: QgsFeature = unconnected_features[0]
            main_pipe: list[QgsFeature] = [f for f in features if f != connecting_pipe]
            return main_pipe, connecting_pipe

        return None, None

    def _find_pipe_by_angle(
        self, point: QgsPointXY, features: list[QgsFeature]
    ) -> tuple[list[QgsFeature], QgsFeature | None]:
        """Identify the main pipe by finding the most collinear pair of features.

        Args:
            point: The intersection point.
            features: A list of three intersecting features.

        Returns:
            A tuple of (main_pipe_features, connecting_pipe_feature). Returns
            ([], None) if identification fails.
        """
        feature_endpoints: dict[int, QgsPointXY | None] = {
            f.id(): self.get_other_endpoint(f, point) for f in features
        }

        max_angle = -1.0
        main_pipe: list[QgsFeature] = []

        for i in range(len(features)):
            for j in range(i + 1, len(features)):
                f1, f2 = features[i], features[j]
                p1, p2 = feature_endpoints.get(f1.id()), feature_endpoints.get(f2.id())

                if p1 and p2:
                    angle = self.calculate_angle(p1, point, p2)
                    if angle > max_angle:
                        max_angle = angle
                        main_pipe = [f1, f2]

        if not main_pipe:
            return [], None

        connecting_pipe: QgsFeature | None = next(
            (f for f in features if f not in main_pipe), None
        )
        return main_pipe, connecting_pipe

    def _create_t_piece(
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

    def _check_and_create_reducer(
        self,
        point: QgsPointXY,
        main_pipe: list[QgsFeature],
        connecting_pipe: QgsFeature,
    ) -> int:
        """Check for dimension changes and creates a reducer if necessary.

        This method handles two scenarios:
        1. A dimension change within the main pipe.
        2. A connecting pipe having a larger diameter than the main pipe.

        Args:
            point: The T-intersection point.
            main_pipe: The two features forming the main pipe.
            connecting_pipe: The feature forming the connecting pipe.

        Returns:
            The number of reducer features created (0 or more).
        """
        if not self.dim_field_name:
            return 0

        dim_main_1: int | None = main_pipe[0].attribute(self.dim_field_name)
        dim_main_2: int | None = main_pipe[1].attribute(self.dim_field_name)

        if not isinstance(dim_main_1, int) or not isinstance(dim_main_2, int):
            return 0

        if abs(dim_main_1 - dim_main_2) > 0:
            return self._create_reducers(point, dim_main_1, dim_main_2, main_pipe)

        dim_conn: int | None = connecting_pipe.attribute(self.dim_field_name)
        if dim_conn is not None and dim_main_1 is not None and dim_conn > dim_main_1:
            # fmt: off
            note_text: str = QCoreApplication.translate("feature_note", "Connecting pipe has a larger diameter than the main pipe.")  # noqa: E501
            # fmt: on
            return self.create_questionable_point(
                point, [*main_pipe, connecting_pipe], note=note_text
            )
        return 0

    def _create_reducers(
        self,
        point: QgsPointXY,
        dim_main_1: float,
        dim_main_2: float,
        main_pipe: list[QgsFeature],
    ) -> int:
        """Create reducers for a dimension change in the main pipe.

        This method calculates how many reducers are needed and creates them
        at appropriate distances from the intersection point.

        Args:
            point: The intersection point.
            dim_main_1: Dimension of the first main pipe feature.
            dim_main_2: Dimension of the second main pipe feature.
            main_pipe: The two features forming the main pipe.

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
            current_large_idx: int = (
                large_idx - i * cont.PipeDimensions.max_dim_jump_reducer
            )
            current_small_idx: int = max(
                small_idx,
                large_idx - (i + 1) * cont.PipeDimensions.max_dim_jump_reducer,
            )

            dim_from: str = f"{pref}{cont.PipeDimensions.diameters[current_large_idx]}"
            dim_to: str = f"{pref}{cont.PipeDimensions.diameters[current_small_idx]}"

            distance: float = cont.Numbers.distance_t_reducer * (i + 1)
            reducer_point: QgsPointXY | None = self._get_point_along_line(
                point, smaller_dim_feature, distance
            )
            if not reducer_point:
                continue

            dims_str: str = cont.Names.dim_separator.join([dim_from, dim_to])
            reducer_attrs = self.get_connected_attributes([smaller_dim_feature])
            reducer_attrs.update(
                {
                    cont.NewLayerFields.type.name: cont.Names.attr_val_type_reducer,
                    cont.NewLayerFields.dimensions.name: dims_str,
                }
            )
            created_count += self.create_feature(
                QgsGeometry.fromPointXY(reducer_point), reducer_attrs
            )

        return created_count

    def _get_point_along_line(
        self, start_point: QgsPointXY, feature: QgsFeature, distance: float
    ) -> QgsPointXY | None:
        """Get a point at a specific distance from the start point along a feature."""
        other_endpoint: QgsPointXY | None = self.get_other_endpoint(
            feature, start_point
        )
        if not other_endpoint:
            return None

        azimuth: float = start_point.azimuth(other_endpoint)
        return start_point.project(distance, azimuth)
