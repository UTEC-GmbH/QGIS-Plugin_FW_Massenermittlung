"""Module: base_finder.py

This module contains the BaseFinder class.
"""

from typing import TYPE_CHECKING

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsFields,
    QgsGeometry,
    QgsPointXY,
    QgsSpatialIndex,
    QgsVectorDataProvider,
    QgsVectorLayer,
    QgsWkbTypes,
)

from modules import constants as cont
from modules.logs_and_errors import log_debug

if TYPE_CHECKING:
    from qgis.core import QgsRectangle


class BaseFinder:
    """A base class for finding features in a vector layer."""

    def __init__(
        self,
        selected_layer: QgsVectorLayer,
        new_layer: QgsVectorLayer,
        selected_layer_index: QgsSpatialIndex,
        dim_field_name: str | None,
    ) -> None:
        """Initialize the BaseFinder class.

        Args:
            selected_layer: The QgsVectorLayer to search within.
            new_layer: The QgsVectorLayer to add new features to.
            selected_layer_index: The spatial index of the selected layer.
            dim_field_name: The name of the dimension field, if found.
        """
        self.selected_layer: QgsVectorLayer = selected_layer
        self.new_layer: QgsVectorLayer = new_layer
        self.selected_layer_index: QgsSpatialIndex = selected_layer_index
        self.dim_field_name: str | None = dim_field_name

    def _create_feature(self, geometry: QgsGeometry, attributes: dict) -> bool:
        """Create a new feature in the new layer."""
        data_provider: QgsVectorDataProvider | None = self.new_layer.dataProvider()
        if data_provider is None:
            log_debug("Data provider is None for new_layer.", Qgis.Critical)
            return False

        layer_fields: QgsFields = self.new_layer.fields()
        field_names: list[str] = [
            layer_fields[idx].name() for idx in range(layer_fields.count())
        ]

        attr_values = [
            attributes.get(field_name)
            for field_name in field_names
            if field_name.lower() != "fid"
        ]
        new_feature = QgsFeature(layer_fields)
        new_feature.setGeometry(geometry)
        new_feature.setAttributes(attr_values)

        return self.new_layer.addFeature(new_feature)

    def _get_connected_attributes(self, connected_features: list[QgsFeature]) -> dict:
        """Get attributes from connected features."""
        connected_ids: list[int] = sorted(
            {feature.attribute("original_fid") for feature in connected_features}
        )
        attributes: dict = {
            cont.NewLayerFields.connected.name: cont.Names.line_separator.join(
                str(id_int) or "???" for id_int in connected_ids
            )
        }
        # Get dimension values if the dimension field was found
        if self.dim_field_name:
            dims: list[str] = sorted(
                {
                    f"{cont.Names.dim_prefix}{feat[self.dim_field_name]}"
                    for feat in connected_features
                    if feat.attribute(self.dim_field_name) is not None
                }
            )
            attributes[cont.NewLayerFields.dimensions.name] = (
                cont.Names.dim_separator.join(dims)
                if len(dims) < cont.Numbers.intersec_t
                else cont.Names.dim_separator.join([dims[0], dims[-1]])
            )
        else:
            attributes[cont.NewLayerFields.dimensions.name] = (
                cont.Names.no_dim_field_found
            )

        return attributes

    def _get_intersecting_features(self, search_geom: QgsGeometry) -> list[QgsFeature]:
        """Get intersecting features for a given geometry."""
        search_rect: QgsRectangle = search_geom.boundingBox()
        candidate_ids: list[int] = self.selected_layer_index.intersects(search_rect)
        return [
            self.selected_layer.getFeature(feat_id)
            for feat_id in candidate_ids
            if self.selected_layer.getFeature(feat_id)
            .geometry()
            .intersects(search_geom)
        ]

    @staticmethod
    def _get_start_end_of_line(feature: QgsFeature) -> list[QgsPointXY]:
        """Get the start and end points of a line feature."""
        points: list = []
        geom: QgsGeometry = feature.geometry()
        if not geom:
            return points

        wkb_type: Qgis.WkbType = geom.wkbType()
        lines = []
        if wkb_type == QgsWkbTypes.LineString:
            lines.append(geom.asPolyline())
        elif wkb_type == QgsWkbTypes.MultiLineString:
            lines.extend(geom.asMultiPolyline())

        for line in lines:
            if len(line) > 1:
                points.extend([line[0], line[-1]])
        return points

    @staticmethod
    def _calculate_angle(p1: QgsPointXY, p2: QgsPointXY, p3: QgsPointXY) -> float:
        """Calculate the angle between three points in degrees using azimuths."""

        # Check for coincident points which would make angle calculation invalid.
        if p2.compare(p1, cont.Numbers.tiny_number) or p2.compare(
            p3, cont.Numbers.tiny_number
        ):
            log_debug("Coinciding points found.", Qgis.Warning)
            return 0.0

        azimuth1: float = p2.azimuth(p1)
        azimuth2: float = p2.azimuth(p3)

        angle: float = abs(azimuth1 - azimuth2)

        if angle > cont.Numbers.circle_semi:
            angle = cont.Numbers.circle_full - angle

        return cont.Numbers.circle_semi - angle

    def _get_adjacent_vertices(
        self, point: QgsPointXY, feature: QgsFeature
    ) -> tuple[QgsPointXY | None, QgsPointXY | None]:
        """Get vertices adjacent to a point on a feature's geometry.

        Finds the vertex on the feature that matches the input point and returns
        the vertices immediately before and after it.

        Args:
            point: The vertex on the feature.
            feature: The feature containing the geometry.

        Returns:
            A tuple containing the previous and next vertices as QgsPointXY.
            Returns (None, None) if the point is an endpoint or not a vertex.
        """
        geom = feature.geometry()
        if not geom:
            return None, None

        # Find the closest vertex on the geometry to the given point
        closest_v, vertex_idx, _, _, dist_sq = geom.closestVertex(point)

        # Ensure the point is actually a vertex (not an intermediate point on a segment)
        if dist_sq > cont.Numbers.tiny_number**2:
            return None, None

        # Check if the vertex is an endpoint of its line part
        if self._is_endpoint(closest_v, feature):
            return None, None

        # Get the vertices before and after the found vertex
        p_before = QgsPointXY(geom.vertexAt(vertex_idx - 1))
        p_after = QgsPointXY(geom.vertexAt(vertex_idx + 1))

        return p_before, p_after

    def _is_endpoint(self, point: QgsPointXY, feature: QgsFeature) -> bool:
        """Check if a point is an endpoint of a feature's line geometry.

        Args:
            point: The point to check.
            feature: The feature to check against.

        Returns:
            True if the point is a start or end point of the feature's geometry,
            False otherwise.
        """
        if start_end_points := self._get_start_end_of_line(feature):
            return any(
                point.compare(endpoint, cont.Numbers.tiny_number)
                for endpoint in start_end_points
            )
        return False
