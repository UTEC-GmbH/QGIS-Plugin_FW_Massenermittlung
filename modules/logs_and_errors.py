"""Module: logs&errors.py

This module contains logging functions and custom error classes.
"""

import inspect
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

from qgis.core import Qgis, QgsMessageLog
from qgis.gui import QgisInterface

iface: QgisInterface | None = None

if TYPE_CHECKING:
    from types import FrameType


def log_debug(message: str, msg_level: Qgis.MessageLevel = Qgis.Info) -> None:
    """Log a debug message.

    :param message: The message to log.
    """
    frame: FrameType | None = inspect.currentframe()
    if frame and frame.f_back:
        filename: str = Path(frame.f_back.f_code.co_filename).name
        lineno: int = frame.f_back.f_lineno
        message = f"{message} ({filename}: {lineno})"

    QgsMessageLog.logMessage(message, "Plugin: Massenermittlung", level=msg_level)


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
        msg_bar.pushMessage("RuntimeError", error_msg, level=Qgis.Critical)

    QgsMessageLog.logMessage(error_msg, "RuntimeError", level=Qgis.Critical)
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
        msg_bar.pushMessage("UserError", error_msg, level=Qgis.Warning)

    QgsMessageLog.logMessage(error_msg, "UserError", level=Qgis.Warning)
    raise CustomUserError(error_msg)
