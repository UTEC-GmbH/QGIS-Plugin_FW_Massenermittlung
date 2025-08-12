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

    bogen: str = "#668000"
    haus: str = "#55ddff"
    t_st: str = "#e2b60a"


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
    field_type: str = "Typ"
    field_winkel: str = "Bogen-Winkel"
    field_verbundene_linien: str = "verbundene Leitungen"
    field_dimension: str = "Dimensionen"

    # Werte der Spalte 'Typ' (Kategorien der Massenermittlung)
    type_value_haus: str = "Hausanschluss"
    type_value_bogen: str = "Bogen"
    type_value_t_st: str = "T-Stück"
    type_value_muffe: str = "Muffe"


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

    # Search radius for finding intersections between lines.
    search_radius: float = 0.05

    # A very small number used for floating point comparisons.
    tiny_number: float = 1e-6

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

    typ = FieldAttributes(Names.field_type, QMeT.Type.QString)
    verbundene_linien = FieldAttributes(
        Names.field_verbundene_linien, QMeT.Type.QString
    )
    dimensionen = FieldAttributes(Names.field_dimension, QMeT.Type.QString)
    winkel = FieldAttributes(Names.field_winkel, QMeT.Type.Double)

    def __iter__(self) -> Generator[FieldAttributes, None, None]:
        """Make the class iterable."""
        for attr_value in self.__class__.__dict__.values():
            if isinstance(attr_value, FieldAttributes):
                yield attr_value
