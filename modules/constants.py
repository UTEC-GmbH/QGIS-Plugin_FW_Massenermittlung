"""Module: constants.py

This module contains constant values.
"""

from collections.abc import Generator
from dataclasses import dataclass

from qgis.PyQt.QtCore import QMetaType as QMeT  # type: ignore[]


@dataclass
class Colours:
    """Class: Colours

    This class contains colour constants.
    """

    bend: str = "#668000"
    house: str = "#55ddff"
    t_piece: str = "#e2b60a"
    connector: str = "#444444"
    reducer: str = "#9900ff"


@dataclass
class Names:
    """Class: Names

    This class contains names.
    """

    new_layer_suffix: str = " - Massenermittlung"
    dim_prefix: str = "DN"
    dim_separator: str = "/"
    line_separator: str = " / "

    # Namen für Saplten der Attributtabelle des alten (gewälten) Layers
    sel_layer_field_dim: str = "diameter"

    # Namen für Spalten der Attributtabelle des neuen Layers
    attr_col_head_type: str = "Typ"
    attr_col_head_bend_angle: str = "Bogen-Winkel"
    attr_col_head_connected: str = "verbundene Leitungen"
    attr_col_head_dimension: str = "Dimensionen"

    # Werte der Spalte 'Typ' in der Attributtabelle (Kategorien der Massenermittlung)
    attr_val_type_house: str = "Hausanschluss"
    attr_val_type_bend: str = "Bogen"
    attr_val_type_t_piece: str = "T-Stück"
    attr_val_type_connector: str = "Muffe"
    attr_val_type_reducer: str = "Reduzierung"


@dataclass
class Numbers:
    """Class: Numbers

    This class contains numeric constants used throughout the plugin.

    """

    circle_full: float = 360  # The number of degrees in a full circle.
    circle_semi: float = 180  # The number of degrees in a semi-circle.

    min_points_line: int = 2  # Minimum number of points for a line.
    min_points_multiline: int = 3  # Minimum number of points for a multiline.

    min_intersec: int = 2  # Minimum number of lines to consider an intersection.
    min_intersec_t: int = 3  # Minimum number of lines to consider a T-intersection.
    min_angle_bogen: int = 15  # Minimum angle to consider a bent line as 'Bogen'.

    distance_t_reducer: float = 0.5  # The distance between T-piece and reducer.

    search_radius: float = 0.05  # Search radius for finding intersections.

    tiny_number: float = 1e-6  # A small number used for floating point comparisons.

    new_layer_font_size: int = 8
    new_layer_label_mask_size: float = 0.8
    new_layer_label_distance: float = 2.5


@dataclass
class FieldAttributes:
    """Class: FieldAttributes

    This class contains the new fields for the new layer.
    """

    name: str
    data_type: QMeT.Type


class NewLayerFields:
    """Constants for layer field attributes, accessible via dot notation."""

    type = FieldAttributes(Names.attr_col_head_type, QMeT.Type.QString)
    connected = FieldAttributes(Names.attr_col_head_connected, QMeT.Type.QString)
    dimensions = FieldAttributes(Names.attr_col_head_dimension, QMeT.Type.QString)
    angle = FieldAttributes(Names.attr_col_head_bend_angle, QMeT.Type.Double)

    def __iter__(self) -> Generator[FieldAttributes, None, None]:
        """Make the class iterable."""
        for attr_value in self.__class__.__dict__.values():
            if isinstance(attr_value, FieldAttributes):
                yield attr_value
