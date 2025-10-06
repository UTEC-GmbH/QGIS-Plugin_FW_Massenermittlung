"""Module: base_finder.py

This module contains the BaseFinder class.
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
    from qgis.core import QgsRectangle


class BaseFinder:
    """A base class for finding features in a vector layer."""

    def __init__(
        self,
        selected_layer: QgsVectorLayer,
        new_layer: QgsVectorLayer,
        selected_layer_index: QgsSpatialIndex,
    ) -> None:
        """Initialize the BaseFinder class.

        :param selected_layer: The QgsVectorLayer to search within.
        :param new_layer: The QgsVectorLayer to add new features to.
        :param selected_layer_index: The spatial index of the selected layer.
        """
        self.selected_layer: QgsVectorLayer = selected_layer
        self.new_layer: QgsVectorLayer = new_layer
        self.selected_layer_index: QgsSpatialIndex = selected_layer_index

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
        # Get dimension values if the field exists
        dim_field: str = cont.Names.sel_layer_field_dim
        if self.selected_layer.fields().lookupField(dim_field) != -1:
            dims: list[str] = sorted(
                {
                    f"{cont.Names.dim_prefix}{feat[dim_field]}"
                    for feat in connected_features
                    if feat.attribute(dim_field) is not None
                }
            )
            attributes[cont.NewLayerFields.dimensions.name] = (
                cont.Names.dim_separator.join(dims)
                if len(dims) < cont.Numbers.min_intersec_t
                else cont.Names.dim_separator.join([dims[0], dims[-1]])
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
    def _get_point_from_intersection(intersection: QgsGeometry) -> QgsPointXY | None:
        """Extract a QgsPointXY from an intersection geometry."""
        if intersection.wkbType() == QgsWkbTypes.Point:
            return intersection.asPoint()
        if (
            intersection.wkbType() == QgsWkbTypes.MultiPoint
            and not intersection.isEmpty()
        ):
            return intersection.asMultiPoint()[0]
        return None

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

    def _is_t_piece(self, point: QgsPointXY) -> bool:
        """Check if a point is a T-intersection."""
        search_geom: QgsGeometry = QgsGeometry.fromPointXY(point).buffer(
            cont.Numbers.search_radius, 5
        )
        intersecting_features: list[QgsFeature] = self._get_intersecting_features(
            search_geom
        )
        return len(intersecting_features) >= cont.Numbers.min_intersec_t

    def _find_intersecting_feature_ids(
        self, point: QgsPointXY, current_feature_id: int
    ) -> list[int]:
        """Find intersecting feature IDs for a given point."""
        search_geom: QgsGeometry = QgsGeometry.fromPointXY(point).buffer(
            cont.Numbers.search_radius, 5
        )
        search_rect: QgsRectangle = search_geom.boundingBox()
        request: QgsFeatureRequest = QgsFeatureRequest().setFilterRect(search_rect)

        candidates = iter(self.selected_layer.getFeatures(request))
        if candidates is not None:
            return [
                feat.id()
                for feat in candidates
                if feat.id() != current_feature_id
                and feat.geometry().intersects(search_geom)
            ]
        return []
