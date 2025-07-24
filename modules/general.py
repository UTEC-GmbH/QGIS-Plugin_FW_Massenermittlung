"""Module: general.py

This module contains general functions.
"""

import contextlib
import re
from typing import NoReturn

from qgis.core import (
    Qgis,
    QgsLayerTreeNode,
    QgsMapLayer,
    QgsMessageLog,
    QgsProject,
)
from qgis.gui import QgisInterface, QgsLayerTreeView


def raise_runtime_error(error_msg: str) -> NoReturn:
    """Log a critical error and raise a RuntimeError.

    This helper function standardizes error handling by ensuring that a critical
    error is raised as a Python exception to halt the current operation.

    :param error_msg: The error message to display and include in the exception.
    :raises RuntimeError: Always raises a RuntimeError with the provided error message.
    """
    QgsMessageLog.logMessage(error_msg, "Error", level=Qgis.Critical)
    raise RuntimeError(error_msg)


def get_current_project() -> QgsProject:
    """Check if a QGIS project is currently open and returns the project instance.

    If no project is open, an error message is logged.

    Returns:
    QgsProject: The current QGIS project instance.
    """
    project: QgsProject | None = QgsProject.instance()
    if project is None:
        raise_runtime_error("No QGIS project is currently open.")

    return project


def get_selected_layer(plugin: QgisInterface) -> QgsMapLayer:
    """Collect the selected layer in the QGIS layer tree view.

    :returns: A list of selected QgsMapLayer objects.
    """
    layer_tree: QgsLayerTreeView | None = plugin.layerTreeView()
    if not layer_tree:
        raise_runtime_error("Could not get layer tree view.")

    selected_nodes: list[QgsLayerTreeNode] = layer_tree.selectedNodes()
    if len(selected_nodes) > 1:
        raise_runtime_error("Multiple layers selected.")
    if not selected_nodes:
        raise_runtime_error("No layer selected.")

    selected_node: QgsLayerTreeNode = next(iter(selected_nodes))
    if not isinstance(selected_node, QgsLayerTreeNode) and selected_node.layer():
        raise_runtime_error("No layer selected.")

    return selected_node.layer()


def fix_layer_name(name: str) -> str:
    """Fix encoding mojibake and sanitize a string to be a valid layer name.

    This function first attempts to fix a common mojibake encoding issue,
    where a UTF-8 string was incorrectly decoded as cp1252
    (for example: 'Ãœ' becomes 'Ü').
    It then sanitizes the string to remove or replace characters
    that might be problematic in layer names,
    especially for file-based formats or databases.

    :param name: The potentially garbled and raw layer name.
    :returns: A fixed and sanitized version of the name.
    """
    fixed_name: str = name
    with contextlib.suppress(UnicodeEncodeError):
        fixed_name = name.encode("cp1252").decode("utf-8")

    # Remove or replace problematic characters
    sanitized_name: str = re.sub(r'[<>:"/\\|?*,]+', "_", fixed_name)

    return sanitized_name
