"""Module: constants.py

This module contains constant values.
"""

from dataclasses import dataclass
from enum import Enum

from qgis.PyQt.QtCore import QVariant as QVar

PROBLEMATIC_FIELD_TYPES: list = [QVar.Map, QVar.List, QVar.StringList]


@dataclass(frozen=True)
class Icons:
    """Class: Icons

    This class contains icon constants.
    """

    Success: str = "🎉"
    Info: str = "💡"
    Warning: str = "💥"
    Critical: str = "☠️"


@dataclass(frozen=True)
class PipeDimensions:
    """Class: PipeDimensions

    This class contains pipe dimensions.
    """

    max_dim_jump_reducer: int = 2

    diameters: tuple = (
        20,
        25,
        32,
        40,
        50,
        65,
        80,
        100,
        125,
        150,
        200,
        250,
        300,
        350,
        400,
        450,
        500,
        600,
        700,
        800,
        900,
        1000,
    )


@dataclass(frozen=True)
class Colours:
    """Class: Colours

    This class contains colour constants.
    """

    bend: str = "#e2b60a"
    house: str = "#55ddff"
    t_piece: str = "#668000"
    reducer: str = "#9900ff"
    connector: str = "#444444"
    questionable: str = "#ff1d1d"


@dataclass(frozen=True)
class Names:
    """Class: Names

    This class contains names.
    """

    new_layer_suffix: str = " - Massenermittlung"
    dim_prefix: str = "DN"
    line_separator: str = " / "

    # Namen für Saplten der Attributtabelle des alten (gewälten) Layers
    sel_layer_field_dim: tuple[str, ...] = ("diameter", "dim", "DN")

    # Werte der Spalte 'Typ' in der Attributtabelle (Kategorien der Massenermittlung)
    attr_val_type_house: str = "Hausanschluss"
    attr_val_type_bend: str = "Bogen"
    attr_val_type_t_piece: str = "T-Stück"
    attr_val_type_connector: str = "Muffe"
    attr_val_type_reducer: str = "Reduzierung"
    attr_val_type_question: str = "Fragwürdiger Punkt"


@dataclass(frozen=True)
class Numbers:
    """Class: Numbers

    This class contains numeric constants used throughout the plugin.

    """

    circle_full: float = 360  # The number of degrees in a full circle.
    circle_semi: float = 180  # The number of degrees in a semi-circle.

    min_points_line: int = 2  # Minimum number of points for a line.
    min_points_multiline: int = 3  # Minimum number of points for a multiline.

    min_intersec: int = 2  # Minimum number of lines to consider an intersection.
    intersec_t: int = 3  # Minimum number of lines to consider a T-intersection.
    min_angle_bend: int = 15  # Minimum angle to consider a bent line as 'Bogen'.

    distance_t_reducer: float = 0.5  # The distance between T-piece and reducer.
    distance_t_bend: float = 0.25  # The distance between T-piece and bend.

    search_radius: float = 0.05  # Search radius for finding intersections.

    tiny_number: float = 1e-6  # A small number used for floating point comparisons.

    new_layer_font_size: int = 8
    new_layer_label_mask_size: float = 0.8
    new_layer_label_distance: float = 2.5


class NewLayerFields(Enum):
    """Constants for layer field attributes, accessible via dot notation.

    This Enum is directly iterable.
    """

    # Enum members are defined as tuples: (display_name, qgis_data_type)
    type: tuple[str, QVar.Type] = ("Typ", QVar.String)
    dim_1: tuple[str, QVar.Type] = ("Dimension 1", QVar.Int)
    dim_2: tuple[str, QVar.Type] = ("Dimension 2", QVar.Int)
    angle: tuple[str, QVar.Type] = ("Bogen-Winkel", QVar.Int)
    connected: tuple[str, QVar.Type] = ("Verbundene Leitungen", QVar.String)
    notes: tuple[str, QVar.Type] = ("Anmerkungen", QVar.String)

    def __init__(self, display_name: str, q_type: QVar.Type) -> None:
        """Initialize the enum member with its attributes."""
        self._display_name: str = display_name
        self._q_type: QVar.Type = q_type

    @property
    def name(self) -> str:
        """The display name of the field."""
        return self._display_name

    @property
    def data_type(self) -> QVar.Type:
        """The QVariant type of the field."""
        return self._q_type
