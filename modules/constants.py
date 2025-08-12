"""Module: constants.py

This module contains constant values.
"""

from collections.abc import Generator
from dataclasses import dataclass

from qgis.PyQt.QtCore import QMetaType as QMeT  # type: ignore[]


@dataclass
class Names:
    """Class: Names

    This class contains names.
    """

    new_layer_suffix: str = " - Massenermittlung"

    # Namen für Saplten der Attributtabelle des alten (gewälten) Layers
    sel_layer_field_dim: str = "diameter"

    # Namen für Spalten der Attributtabelle des neuen Layers
    field_type: str = "Typ"
    field_winkel: str = "Winkel"
    field_verbundene_linien: str = "verbundene Leitungen"
    field_dimension: str = "Dimensionen (DN)"

    # Werte der Spalte 'Typ' (Kategorien der Massenermittlung)
    type_value_haus: str = "Hausanschluss"
    type_value_bogen: str = "Bogen"
    type_value_t_st: str = "T-Stück"
    type_value_muffe: str = "Muffe"


@dataclass
class Numbers:
    """Class: Numbers

    This class contains numeric constants used throughout the plugin.

    Attributes:
        circle_full (float): The number of degrees in a full circle.
        circle_semi (float): The number of degrees in a semi-circle.
        min_points_line (int): Minimum number of points for a line.
        min_points_multiline (int): Minimum number of points for a multiline.
        min_intersec (int): Minimum number of lines to consider an intersection.
        min_intersec_t (int): Minimum number of lines to consider a T-intersection.
        min_angle_bogen (int): Minimum angle to consider a bent line as 'Bogen'.
        search_radius (float): Search radius for finding intersections betweenlines.
        tiny_number (float): A very small number used for floating pointcomparisons.
    """

    circle_full: float = 360
    circle_semi: float = 180

    min_points_line: int = 2
    min_points_multiline: int = 3

    min_intersec: int = 2
    min_intersec_t: int = 3
    min_angle_bogen: int = 15

    search_radius: float = 0.05
    tiny_number: float = 1e-6


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
    winkel = FieldAttributes(Names.field_winkel, QMeT.Type.Double)
    verbundene_linien = FieldAttributes(
        Names.field_verbundene_linien, QMeT.Type.QString
    )
    dimensionen = FieldAttributes(Names.field_dimension, QMeT.Type.QString)

    def __iter__(self) -> Generator[FieldAttributes, None, None]:
        """Make the class iterable."""
        for attr_value in self.__class__.__dict__.values():
            if isinstance(attr_value, FieldAttributes):
                yield attr_value
