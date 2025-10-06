"""Module: t_piece_finder.py

This module contains the TPieceFinder class.
"""

import math
from typing import Callable

from qgis.core import Qgis, QgsFeature, QgsGeometry, QgsPointXY

from modules import constants as cont
from modules.logs_and_errors import log_debug

from .base_finder import BaseFinder


class TPieceFinder(BaseFinder):
    """A class to find T-pieces."""

    def find(
        self, features: list[QgsFeature], progress_callback: Callable | None = None
    ) -> int:
        """Find 3-way (or more) intersections of lines."""
        number_of_new_points = 0
        checked_intersections: set = set()

        for feature in features:
            geom: QgsGeometry = feature.geometry()
            candidate_ids: list[int] = self.selected_layer_index.intersects(
                geom.boundingBox().buffered(cont.Numbers.search_radius)
            )

            for candidate_id in candidate_ids:
                if candidate_id <= feature.id():
                    continue

                candidate_feature: QgsFeature = self.selected_layer.getFeature(
                    candidate_id
                )
                candidate_geom: QgsGeometry = candidate_feature.geometry()

                if not geom.intersects(candidate_geom):
                    continue

                intersection: QgsGeometry = geom.intersection(candidate_geom)
                intersection_point: QgsPointXY | None = (
                    self._get_point_from_intersection(intersection)
                )

                if not intersection_point:
                    continue

                point_key: tuple[float, float] = (
                    round(intersection_point.x(), 4),
                    round(intersection_point.y(), 4),
                )
                if point_key in checked_intersections:
                    continue

                checked_intersections.add(point_key)

                number_of_new_points += self._process_intersection(
                    intersection, intersection_point
                )

        if progress_callback:
            progress_callback()

        log_debug(f"Checked {len(features)} intersections.")

        return number_of_new_points

    def _is_questionable_intersection(
        self,
        intersection_point: QgsPointXY,
        intersecting_features: list[QgsFeature],
    ) -> bool:
        """Check if an intersection is questionable
        by looking for nearby poorly drawn lines.
        """
        for feature in intersecting_features:
            for point in self._get_start_end_of_line(feature):
                distance: float = intersection_point.distance(point)
                if 0 < distance < cont.Numbers.search_radius:
                    return True
        return False

    def _process_intersection(
        self, intersection: QgsGeometry, intersection_point: QgsPointXY
    ) -> int:
        """Process a single intersection point.

        Creates T-pieces and reducers based on the number of intersecting lines.
        For n intersecting lines, n-2 T-pieces are created.
        """
        search_geom: QgsGeometry = QgsGeometry.fromPointXY(intersection_point).buffer(
            cont.Numbers.search_radius, 5
        )
        intersecting_features: list[QgsFeature] = self._get_intersecting_features(
            search_geom
        )

        n_intersections: int = len(intersecting_features)

        if n_intersections < cont.Numbers.min_intersec_t:
            return 0

        if self._is_questionable_intersection(
            intersection_point, intersecting_features
        ):
            attributes: dict[str, str] = {
                cont.NewLayerFields.type.name: cont.Names.attr_val_type_question
            }
            attributes |= self._get_connected_attributes(intersecting_features)
            if self._create_feature(
                QgsGeometry.fromPointXY(intersection_point), attributes
            ):
                return 1
            return 0

        num_t_pieces: int = n_intersections - 2
        created_count = 0

        # Small offset to place T-pieces next to each other if there are more than one
        offset_dist: float = cont.Numbers.distance_t_reducer / 1.5

        for i in range(num_t_pieces):
            if num_t_pieces > 1:
                angle: float = i * (2 * math.pi / num_t_pieces)
                offset_x: float = offset_dist * math.cos(angle)
                offset_y: float = offset_dist * math.sin(angle)
                t_piece_point = QgsPointXY(
                    intersection_point.x() + offset_x, intersection_point.y() + offset_y
                )
                t_piece_geom: QgsGeometry = QgsGeometry.fromPointXY(t_piece_point)
            else:
                t_piece_point: QgsPointXY = intersection_point
                t_piece_geom = intersection

            if self._create_t_piece_and_reducers(
                t_piece_geom, t_piece_point, intersecting_features
            ):
                created_count += 1

        return created_count

    def _create_t_piece_and_reducers(
        self,
        t_piece_geom: QgsGeometry,
        t_piece_point: QgsPointXY,
        intersecting_features: list[QgsFeature],
    ) -> bool:
        """Create a T-piece and its associated reducers."""
        dim_field: str = cont.Names.sel_layer_field_dim
        dimensions: dict[int, float] = {}
        for f in intersecting_features:
            dim_val = f.attribute(dim_field)
            if dim_val is not None:
                try:
                    dimensions[f.id()] = float(dim_val)
                except (ValueError, TypeError):
                    log_debug(
                        f"Could not parse dimension '{dim_val}' for feature {f.id()}",
                        Qgis.Warning,
                    )

        if not dimensions:
            return False

        unique_dimensions: set[float] = set(dimensions.values())
        max_dim: float = max(unique_dimensions)
        min_dim: float = min(unique_dimensions)

        attributes: dict[str, str] = {
            cont.NewLayerFields.type.name: cont.Names.attr_val_type_t_piece,
            cont.NewLayerFields.dimensions.name: (
                f"{cont.Names.dim_prefix}{int(max_dim)}/"
                f"{cont.Names.dim_prefix}{int(min_dim)}"
            ),
        }
        attributes |= self._get_connected_attributes(intersecting_features)

        if not self._create_feature(t_piece_geom, attributes):
            return False

        # A reducer is only needed if there are at least 3 different dimensions
        if len(unique_dimensions) < cont.Numbers.min_dim_reducer:
            return True

        middle_dimensions: set[float] = {
            d for d in unique_dimensions if d not in [max_dim, min_dim]
        }

        for f in intersecting_features:
            f_id: int = f.id()
            if f_id not in dimensions:
                continue

            line_dim: float = dimensions[f_id]

            if line_dim in middle_dimensions:
                # Reducer is from max_dim to the middle dimension
                self._create_reducer_for_line(f, t_piece_point, max_dim, line_dim)

        return True

    def _create_reducer_for_line(
        self,
        feature: QgsFeature,
        intersection_point: QgsPointXY,
        from_dim: float,
        to_dim: float,
    ) -> None:
        """Create one or more reducers on a given line to bridge the dimension gap."""
        line_geom: QgsGeometry = feature.geometry()
        if not line_geom or line_geom.isNull():
            return

        # --- Find where to place reducers ---
        line_points: list[QgsPointXY] = line_geom.asPolyline()
        if not line_points:
            return

        start_point = QgsPointXY(line_points[0])
        is_at_start: bool = (
            intersection_point.distance(start_point) < cont.Numbers.search_radius
        )

        # --- Get dimension lists and jump settings ---
        all_dims: tuple = cont.PipeDimensions.diameters
        max_jump: int = cont.PipeDimensions.max_dim_jump_reducer

        try:
            from_idx: int = all_dims.index(int(from_dim))
            to_idx: int = all_dims.index(int(to_dim))
        except ValueError:
            # If dimensions are not in the standard list,
            # create a single reducer as a fallback.
            self._create_single_reducer(
                feature, line_geom, is_at_start, from_dim, to_dim
            )
            return

        # --- Iterate and create chained reducers ---
        current_idx: int = from_idx
        reducer_distance: float = cont.Numbers.distance_t_reducer

        if current_idx <= to_idx:
            self._create_single_reducer(
                feature, line_geom, is_at_start, from_dim, to_dim
            )
            return

        while current_idx > to_idx:
            # Determine the next dimension in the chain
            next_idx = max(current_idx - max_jump, to_idx)

            current_dim = all_dims[current_idx]
            next_dim = all_dims[next_idx]

            # Check if the line is long enough for the next reducer
            if line_geom.length() <= reducer_distance:
                # Not enough space for more reducers,
                # create one last one to the final dim and stop.
                self._create_single_reducer(
                    feature,
                    line_geom,
                    is_at_start,
                    current_dim,
                    to_dim,
                    reducer_distance,
                )
                break

            # Create the reducer for the current step in the chain
            self._create_single_reducer(
                feature, line_geom, is_at_start, current_dim, next_dim, reducer_distance
            )

            # Update for the next iteration
            current_idx = next_idx
            reducer_distance += cont.Numbers.distance_t_reducer

            if current_idx == to_idx:
                break

    def _create_single_reducer(
        self,
        feature: QgsFeature,
        line_geom: QgsGeometry,
        is_at_start: bool,
        dim1: float,
        dim2: float,
        distance: float | None = None,
    ) -> None:
        """Create a single reducer feature on a line at a given distance."""
        if distance is None:
            distance = cont.Numbers.distance_t_reducer

        if line_geom.length() <= distance:
            return

        if is_at_start:
            # Interpolate from the start of the line
            reducer_geom = line_geom.interpolate(distance)
        else:
            # Interpolate from the end of the line
            reducer_geom = line_geom.interpolate(line_geom.length() - distance)

        reducer_point = reducer_geom.asPoint()
        if not reducer_point or reducer_point.isEmpty():
            return

        reducer_attributes: dict[str, str] = {
            cont.NewLayerFields.type.name: cont.Names.attr_val_type_reducer,
            cont.NewLayerFields.dimensions.name: (
                f"{cont.Names.dim_prefix}{int(dim1)}/{cont.Names.dim_prefix}{int(dim2)}"
            ),
            cont.NewLayerFields.connected.name: str(feature.attribute("original_fid"))
            or "???",
        }
        self._create_feature(
            QgsGeometry.fromPointXY(reducer_point),
            reducer_attributes,
        )
