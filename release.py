"""A script to automate the plugin release process.

This script provides a single source of truth for the plugin's version number,
reading it from metadata.txt and automatically updating the private repository's
plugins.xml file. It then compiles and packages the plugin.

To use:
1. Update the 'version' in metadata.txt.
2. Run this script from the OSGeo4W Shell: python release.py
"""

import configparser
import logging
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from defusedxml import ElementTree as ElTr

# --- Configuration ---
METADATA_FILE: Path = Path("metadata.txt")
PLUGINS_XML_FILE: Path = Path("plugins.xml")

# --- Logger ---
logger: logging.Logger = logging.getLogger(__name__)


class ReleaseScriptError(Exception):
    """Custom exception for errors during the release process."""


def get_plugin_metadata() -> tuple[str, str]:
    """Read the plugin name and version from the metadata.txt file.

    Returns:
        A tuple containing the plugin name and version string.

    Raises:
        ReleaseScriptError: If the metadata file is not found or is missing keys.
    """
    if not METADATA_FILE.exists():
        msg = f"Metadata file not found at '{METADATA_FILE}'"
        raise ReleaseScriptError(msg)

    config = configparser.ConfigParser()
    config.read(METADATA_FILE)
    try:
        name: str = config.get("general", "name")
        version: str = config.get("general", "version")
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        msg = (
            "Could not find '[general]' section or required keys ('name', "
            f"'version') in {METADATA_FILE}."
        )
        logger.exception("❌ %s", msg)
        raise ReleaseScriptError(msg) from e
    else:
        logger.info(
            "✅ Found plugin '%s' version '%s' in %s",
            name,
            version,
            METADATA_FILE,
        )
        return name, version


def update_repository_file(plugin_name: str, version: str) -> None:
    """Update the version, filename, and download URL in the plugins.xml file.

    Args:
        plugin_name: The name of the plugin.
        version: The new version string to apply.

    Raises:
        ReleaseScriptError: If plugins.xml or required tags are not found.
    """
    logger.info("Updating %s to version %s...", PLUGINS_XML_FILE, version)

    if not PLUGINS_XML_FILE.exists():
        msg = f"Repository file not found at '{PLUGINS_XML_FILE}'"
        raise ReleaseScriptError(msg)

    try:
        tree: ElTr.ElementTree = ElTr.parse(PLUGINS_XML_FILE)  # pyright: ignore[reportAttributeAccessIssue]
        root: ElTr.Element = tree.getroot()  # pyright: ignore[reportAttributeAccessIssue]

        plugin_node = next(
            (
                node
                for node in root.findall("pyqgis_plugin")
                if node.get("name") == plugin_name
            ),
            None,
        )
        if plugin_node is None:
            logger.error(
                "❌ Could not find plugin '%s' in %s",
                plugin_name,
                PLUGINS_XML_FILE,
            )
            msg = f"Plugin '{plugin_name}' not in repository XML."
            raise ReleaseScriptError(msg)

        plugin_node.set("version", version)
        if (version_tag := plugin_node.find("version")) is not None:
            version_tag.text = version

        new_zip_filename: str = f"{plugin_name}-{version}.zip"
        if (filename_tag := plugin_node.find("file_name")) is not None:
            filename_tag.text = new_zip_filename

        if (
            download_url_tag := plugin_node.find("download_url")
        ) is not None and download_url_tag.text:
            old_url: str = download_url_tag.text
            new_url: str = re.sub(r"/[^/]+\.zip$", f"/{new_zip_filename}", old_url)
            download_url_tag.text = new_url

        tree.write(PLUGINS_XML_FILE, encoding="utf-8", xml_declaration=True)
        logger.info("✅ Successfully updated %s", PLUGINS_XML_FILE)

    except ElTr.ParseError as e:
        msg = f"Error parsing {PLUGINS_XML_FILE}."
        logger.exception("❌ %s", msg)
        raise ReleaseScriptError(msg) from e


def run_command(command: list[str], shell: bool = False) -> None:
    """Run a command in a subprocess and checks for errors."""
    logger.info("\n▶️ Running command: %s", " ".join(command))
    try:
        # Create a copy of the current environment to avoid modifying the
        # parent process's environment.
        env = os.environ.copy()

        # In OSGeo4W, many necessary command-line tools (like 'zip' or '7z')
        # reside in the same 'bin' directory as the Python executable.
        # We prepend this directory to the PATH to ensure these tools are found
        # by subprocesses like pb_tool.
        python_bin_dir = str(Path(sys.executable).parent)
        if "PATH" in env:
            # os.pathsep is ';' on Windows and ':' on Linux/macOS
            if python_bin_dir not in env["PATH"].split(os.pathsep):
                env["PATH"] = f"{python_bin_dir}{os.pathsep}{env['PATH']}"
        else:
            env["PATH"] = python_bin_dir

        result = subprocess.run(  # noqa: S603
            command,
            check=True,
            capture_output=True,
            text=True,
            shell=shell,
            env=env,
        )
        if result.stdout:
            logger.info(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        logger.exception("❌ Error running command: %s", " ".join(command))
        # Stderr is often the most useful part of a subprocess error
        if e.stderr:
            logger.exception("Stderr: %s", e.stderr.strip())
        msg = f"Command '{' '.join(command)}' failed."
        raise ReleaseScriptError(msg) from e


def package_plugin_from_config(plugin_name: str, version: str) -> None:
    """Create a zip archive of the plugin from pb_tool.cfg.

    This function reads the packaging configuration from 'pb_tool.cfg',
    collects the specified files and directories, and creates a zip archive
    in the 'packages/' directory. This removes the dependency on an external
    'zip' or '7z' command-line tool.

    Args:
        plugin_name: The name of the plugin, used for the zip file.
        version: The plugin version, used for the zip file.

    Raises:
        ReleaseScriptError: If 'pb_tool.cfg' is not found or is invalid.
    """
    logger.info("\n▶️ Packaging plugin using built-in zip functionality...")
    pb_tool_cfg_path = Path("pb_tool.cfg")
    if not pb_tool_cfg_path.exists():
        msg = f"Configuration file not found at '{pb_tool_cfg_path}'"
        raise ReleaseScriptError(msg)

    config = configparser.ConfigParser()
    config.read(pb_tool_cfg_path)

    try:
        # The root directory name inside the zip file
        plugin_zip_dir = config.get("plugin", "name")

        # --- Collect files and directories from config ---
        files_to_zip: list[str] = []
        if config.has_option("files", "python_files"):
            files_to_zip.extend(config.get("files", "python_files").split())
        if config.has_option("files", "extras"):
            files_to_zip.extend(config.get("files", "extras").split())

        dirs_to_zip: list[str] = []
        if config.has_option("files", "extra_dirs"):
            dirs_to_zip.extend(config.get("files", "extra_dirs").split())

        # --- Create the zip archive ---
        packages_dir = Path("packages")
        packages_dir.mkdir(exist_ok=True)
        zip_path = packages_dir / f"{plugin_name}-{version}.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            # Add specified individual files
            for file_str in files_to_zip:
                file_path = Path(file_str)
                if file_path.exists():
                    arcname = Path(plugin_zip_dir) / file_path
                    zipf.write(file_path, arcname)
                else:
                    logger.warning(
                        "⚠️ File '%s' from pb_tool.cfg not found, skipping.",
                        file_path,
                    )

            # Add specified directories recursively
            for dir_str in dirs_to_zip:
                dir_path = Path(dir_str)
                if not dir_path.is_dir():
                    logger.warning(
                        "⚠️ Directory '%s' from pb_tool.cfg not found, skipping.",
                        dir_path,
                    )
                    continue

                for root, _, files in os.walk(dir_path):
                    for file in files:
                        if "__pycache__" in root or file.endswith(".pyc"):
                            continue
                        file_path = Path(root) / file
                        arcname = Path(plugin_zip_dir) / file_path
                        zipf.write(file_path, arcname)

        logger.info("✅ Successfully created plugin package at: %s", zip_path)

    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        msg = f"Invalid 'pb_tool.cfg'. Missing section or option: {e}"
        raise ReleaseScriptError(msg) from e


def copy_repository_file_to_packages() -> None:
    """Copy the updated plugins.xml to the packages directory.

    This centralizes all release artifacts into a single folder, simplifying
    the deployment process.

    Raises:
        ReleaseScriptError: If the copy operation fails.
    """
    logger.info("\n▶️ Copying %s to 'packages/' directory...", PLUGINS_XML_FILE)
    packages_dir = Path("packages")
    if not packages_dir.is_dir():
        msg = f"Packages directory '{packages_dir}' not found. Cannot copy file."
        raise ReleaseScriptError(msg)

    try:
        destination_path = packages_dir / PLUGINS_XML_FILE.name
        shutil.copy2(PLUGINS_XML_FILE, destination_path)
        logger.info(
            "✅ Successfully copied %s to %s",
            PLUGINS_XML_FILE,
            destination_path,
        )
    except (shutil.Error, OSError) as e:
        msg = (
            f"Failed to copy {PLUGINS_XML_FILE} to {packages_dir}. "
            "Check file permissions."
        )
        raise ReleaseScriptError(msg) from e


def setup_logging() -> None:
    """Configure the module's logger to print to the console."""
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def run_release_process() -> None:
    """Automate the plugin release process.

    This main function orchestrates the entire release process:
    1. Reads metadata.
    2. Updates the repository XML.
    3. Compiles resources and translations.
    4. Packages the plugin into a zip file.
    5. Copies the repository XML to the packages directory.

    Raises:
        ReleaseScriptError: If any step in the release process fails.
    """
    plugin_name, version = get_plugin_metadata()
    update_repository_file(plugin_name, version)
    # The 'shell=True' is required on Windows to run .bat files correctly
    # from the PATH. This is safe as the command is a static string.
    run_command(["compile.bat"], shell=True)

    package_plugin_from_config(plugin_name, version)
    copy_repository_file_to_packages()

    logger.info("\n🎉 --- Release process complete! --- 🎉")
    logger.info("Next steps:")
    logger.info(
        "  - Copy all files from the 'packages/' directory to the shared drive."
    )


def main() -> int:
    """CLI entry point. Sets up logging and runs the release process.

    Returns:
        An exit code: 0 for success, 1 for failure.
    """
    setup_logging()
    try:
        run_release_process()
    except ReleaseScriptError as e:
        logger.critical("❌ A critical error occurred: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
