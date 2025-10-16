"""Module: vector_analysis_tools.py

This module contains the VectorAnalysisTools class.
"""

from typing import TYPE_CHECKING

from qgis.core import (
    Qgis,
    QgsFeature,
    QgsFeatureRequest,
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
    from collections.abc import Iterable

    from qgis.core import QgsRectangle


class VectorAnalysisTools:
    """A base class for finding features in a vector layer."""

    def __init__(
        self,
        selected_layer: QgsVectorLayer,
        temp_point_layer: QgsVectorLayer,
    ) -> None:
        """Initialize the VectorAnalysisTools class.

        Args:
            selected_layer: The QgsVectorLayer to search within.
            temp_point_layer: The temporary QgsVectorLayer to add new features to.
        """
        self.selected_layer: QgsVectorLayer = selected_layer
        self.new_layer: QgsVectorLayer = temp_point_layer
        log_debug(f"Creating spatial index for layer '{selected_layer.name()}'.")
        request: QgsFeatureRequest = QgsFeatureRequest().setNoAttributes()
        self.selected_layer_index: QgsSpatialIndex = QgsSpatialIndex(
            selected_layer.getFeatures(request)
        )
        log_debug("Spatial index created.", Qgis.Success)
        self.dim_field_name: str | None = self.find_dim_field_name(selected_layer)

    @staticmethod
    def find_dim_field_name(layer: QgsVectorLayer) -> str | None:
        """Find the first matching dimension field name from the constants.

        Args:
            layer: The layer to search for the dimension field.

        Returns:
            The name of the found field, or None if no match is found.
        """
        layer_fields: QgsFields = layer.fields()
        field_names: Iterable[str] = cont.Names.sel_layer_field_dim
        found_name: str | None = next(
            (name for name in field_names if layer_fields.lookupField(name) != -1),
            None,
        )

        if found_name:
            log_debug(f"Found dimension field: '{found_name}'", Qgis.Success)
        else:
            log_debug("No dimension field found in the selected layer.", Qgis.Warning)
        return found_name

    def create_feature(self, geometry: QgsGeometry, attributes: dict) -> bool:
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

    def get_connected_attributes(self, connected_features: list[QgsFeature]) -> dict:
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
                },
                reverse=True,
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

    def get_intersecting_features(self, search_geom: QgsGeometry) -> list[QgsFeature]:
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
    def get_start_end_of_line(feature: QgsFeature) -> list[QgsPointXY]:
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
    def calculate_angle(p1: QgsPointXY, p2: QgsPointXY, p3: QgsPointXY) -> float:
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

        return angle

    def get_adjacent_vertices(
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
        geom: QgsGeometry = feature.geometry()
        if not geom:
            return None, None

        # Find the closest vertex on the geometry to the given point
        closest_v, vertex_idx, _, _, dist_sq = geom.closestVertex(point)

        # Ensure the point is actually a vertex (not an intermediate point on a segment)
        if dist_sq > cont.Numbers.tiny_number**2:
            return None, None

        # Check if the vertex is an endpoint of its line part
        if self.is_endpoint(closest_v, feature):
            return None, None

        # Get the vertices before and after the found vertex
        p_before = QgsPointXY(geom.vertexAt(vertex_idx - 1))
        p_after = QgsPointXY(geom.vertexAt(vertex_idx + 1))

        return p_before, p_after

    def is_endpoint(self, point: QgsPointXY, feature: QgsFeature) -> bool:
        """Check if a point is an endpoint of a feature's line geometry.

        Args:
            point: The point to check.
            feature: The feature to check against.

        Returns:
            True if the point is a start or end point of the feature's geometry,
            False otherwise.
        """
        if start_end_points := self.get_start_end_of_line(feature):
            return any(
                point.compare(endpoint, cont.Numbers.tiny_number)
                for endpoint in start_end_points
            )
        return False

    def get_other_endpoint(
        self, feature: QgsFeature, reference_point: QgsPointXY
    ) -> QgsPointXY | None:
        """Get the endpoint of a line feature that is furthest from a reference point.

        This is useful for finding the "remote" end of a line when you have an
        intersection point near one of its ends.

        Args:
            feature: The line feature.
            reference_point: The point to measure distance from.

        Returns:
            The QgsPointXY of the other endpoint, or None if endpoints cannot be
            determined.
        """
        endpoints: list[QgsPointXY] = self.get_start_end_of_line(feature)
        if len(endpoints) != 2:  # noqa: PLR2004
            return None

        p1, p2 = endpoints
        return p2 if p1.distance(reference_point) < p2.distance(reference_point) else p1

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
