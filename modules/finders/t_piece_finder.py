"""Module: t_piece_finder.py

This module contains the TPieceFinder class.
"""

from qgis.core import Qgis, QgsFeature, QgsGeometry, QgsPointXY
from qgis.PyQt.QtCore import (
    QCoreApplication,  # type: ignore[reportAttributeAccessIssue]
)

from modules import constants as cont
from modules.logs_and_errors import log_debug, log_summary

from .base_finder import BaseFinder


class TPieceFinder(BaseFinder):
    """A class to find T-pieces."""

    def find(self, features: list[QgsFeature]) -> int:
        """Find 3-way (or more) intersections of lines."""
        number_of_new_points = 0
        checked_intersections: set = set()
        dim_field: str = cont.Names.sel_layer_field_dim

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

                search_geom: QgsGeometry = QgsGeometry.fromPointXY(
                    intersection_point
                ).buffer(cont.Numbers.search_radius, 5)
                intersecting_features: list[QgsFeature] = (
                    self._get_intersecting_features(search_geom)
                )

                if len(intersecting_features) >= cont.Numbers.min_intersec_t:
                    attributes: dict[str, str] = {
                        cont.NewLayerFields.type.name: cont.Names.attr_val_type_t_piece
                    }
                    attributes |= self._get_connected_attributes(intersecting_features)
                    if self._create_feature(intersection, attributes):
                        number_of_new_points += 1

                    # Add reducers if dimensions differ
                    dimensions: dict[int, float] = {}
                    for f in intersecting_features:
                        dim_val = f.attribute(dim_field)
                        if dim_val is not None:
                            try:
                                dimensions[f.id()] = float(dim_val)
                            except (ValueError, TypeError):
                                log_debug(
                                    f"Could not parse dimension '{dim_val}' "
                                    f"for feature {f.id()}",
                                    Qgis.Warning,
                                )

                    if not dimensions:
                        continue

                    max_dim: float = max(dimensions.values())

                    for f in intersecting_features:
                        f_id: int = f.id()
                        if f_id not in dimensions:
                            continue

                        line_dim: float = dimensions[f_id]

                        if line_dim < max_dim:
                            line_geom: QgsGeometry = f.geometry()
                            if not line_geom or line_geom.isNull():
                                continue

                            line_points: list[QgsPointXY] = line_geom.asPolyline()
                            if not line_points:
                                continue

                            start_point: QgsPointXY = QgsPointXY(line_points[0])
                            end_point: QgsPointXY = QgsPointXY(line_points[-1])

                            dist_to_start: float = intersection_point.distance(
                                start_point
                            )
                            dist_to_end: float = intersection_point.distance(end_point)

                            reducer_point: QgsPointXY | None = None
                            if dist_to_start < cont.Numbers.search_radius:
                                if line_geom.length() > cont.Numbers.distance_t_reducer:
                                    reducer_geom: QgsGeometry = line_geom.interpolate(
                                        cont.Numbers.distance_t_reducer
                                    )
                                    reducer_point = reducer_geom.asPoint()
                            elif (
                                dist_to_end < cont.Numbers.search_radius
                                and line_geom.length() > cont.Numbers.distance_t_reducer
                            ):
                                reducer_geom: QgsGeometry = line_geom.interpolate(
                                    line_geom.length() - cont.Numbers.distance_t_reducer
                                )
                                reducer_point = reducer_geom.asPoint()

                            if reducer_point:
                                reducer_attributes: dict[str, str] = {
                                    cont.NewLayerFields.type.name: (
                                        cont.Names.attr_val_type_reducer
                                    ),
                                    cont.NewLayerFields.dimensions.name: (
                                        f"{cont.Names.dim_prefix}{int(max_dim)}/"
                                        f"{cont.Names.dim_prefix}{int(line_dim)}"
                                    ),
                                    cont.NewLayerFields.connected.name: str(f.id()),
                                }
                                self._create_feature(
                                    QgsGeometry.fromPointXY(reducer_point),
                                    reducer_attributes,
                                )

        log_summary(
            QCoreApplication.translate("log", "T-pieces"),
            len(features),
            number_of_new_points,
        )
        return number_of_new_points
