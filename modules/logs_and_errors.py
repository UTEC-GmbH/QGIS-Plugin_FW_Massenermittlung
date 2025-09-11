"""Module: logs&errors.py

This module contains logging functions and custom error classes.
"""

import inspect
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

from qgis.core import Qgis, QgsMessageLog
from qgis.gui import QgisInterface
from qgis.PyQt.QtCore import (
    QCoreApplication,  # type: ignore[reportAttributeAccessIssue]
)

iface: QgisInterface | None = None

if TYPE_CHECKING:
    from types import FrameType


def log_debug(message: str, msg_level: Qgis.MessageLevel = Qgis.Info) -> None:
    """Log a debug message.

    :param message: The message to log.
    """
    QgsMessageLog.logMessage(message, "Massenermittlung", level=msg_level)


def log_summary(item_name: str, checked_count: int, found_count: int) -> None:
    """Log a summary message for a feature finding operation."""

    # TRANSLATORS: {0} is the item name (e.g., 'T-piece'),
    # {1} is the number of items checked, {2} is the number of items found.

    if found_count:
        message = QCoreApplication.translate(
            "log", "{0}: {1} lines checked → {2} items found."
        ).format(item_name, checked_count, found_count)
        log_debug(message, Qgis.Success)
    else:
        message = QCoreApplication.translate(
            "log", "{0}: {1} lines checked → No items found."
        ).format(item_name, checked_count)
        log_debug(message, Qgis.Warning)


class CustomRuntimeError(Exception):
    """Custom exception for runtime errors in the plugin."""


def raise_runtime_error(error_msg: str) -> NoReturn:
    """Log a critical error and raise a RuntimeError.

    This helper function standardizes error handling by ensuring that a critical
    error is raised as a Python exception to halt the current operation.

    :param error_msg: The error message to display and include in the exception.
    :raises RuntimeError: Always raises a RuntimeError with the provided error message.
    """
    frame: FrameType | None = inspect.currentframe()
    if frame and frame.f_back:
        filename: str = Path(frame.f_back.f_code.co_filename).name
        lineno: int = frame.f_back.f_lineno
        error_msg = f"{error_msg} ({filename}: {lineno})"

    if iface and (msg_bar := iface.messageBar()):
        msg_bar.pushMessage("Error", error_msg, level=Qgis.Critical)

    QgsMessageLog.logMessage(error_msg, "Error", level=Qgis.Critical)
    raise CustomRuntimeError(error_msg)


class CustomUserError(Exception):
    """Custom exception for user-related errors in the plugin."""


def raise_user_error(error_msg: str) -> NoReturn:
    """Log a warning message and raise a UserError.

    This helper function standardizes error handling by ensuring that a warning
    is raised to halt the current operation because of a user error.

    :param error_msg: The error message to display and include in the exception.
    :raises CustomUserError: Always raises a UserError with the provided error message.
    """

    if iface and (msg_bar := iface.messageBar()):
        msg_bar.pushMessage("Error", error_msg, level=Qgis.Critical)

    QgsMessageLog.logMessage(error_msg, "Error", level=Qgis.Critical)
    raise CustomUserError(error_msg)
