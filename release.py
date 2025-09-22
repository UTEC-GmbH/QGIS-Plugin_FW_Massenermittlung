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
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import TypedDict

from defusedxml import ElementTree as ElTr

# --- Configuration ---
METADATA_FILE: Path = Path("metadata.txt")
PLUGINS_XML_FILE: Path = Path("packages") / "plugins.xml"

# --- Logger ---
logger: logging.Logger = logging.getLogger(__name__)


class PluginMetadata(TypedDict):
    """A dictionary representing the plugin's metadata."""

    name: str
    version: str
    url_base: str
    description: str
    about: str
    qgis_minimum_version: str
    author: str
    email: str


class ReleaseScriptError(Exception):
    """Custom exception for errors during the release process."""


def get_plugin_metadata() -> PluginMetadata:
    """Read plugin metadata from the metadata.txt file.

    Returns:
        A dictionary containing the plugin's core metadata.

    Raises:
        ReleaseScriptError: If the metadata file is not found or is missing keys.
    """
    if not METADATA_FILE.exists():
        msg = f"Metadata file not found at '{METADATA_FILE}'"
        raise ReleaseScriptError(msg)

    config = configparser.ConfigParser()
    config.read(METADATA_FILE)
    try:
        metadata: PluginMetadata = {
            "name": config.get("general", "name"),
            "version": config.get("general", "version"),
            "url_base": config.get("general", "download_url_base"),
            "description": config.get("general", "description"),
            "about": config.get("general", "about"),
            "qgis_minimum_version": config.get("general", "qgisMinimumVersion"),
            "author": config.get("general", "author"),
            "email": config.get("general", "email"),
        }
    except configparser.NoSectionError as e:
        msg = f"Could not find required section '[{e.section}]' in {METADATA_FILE}."
        logger.exception("❌ %s", msg)
        raise ReleaseScriptError(msg) from e
    except configparser.NoOptionError as e:
        msg = (
            f"Missing required key '{e.option}' in section '[{e.section}]' "
            f"in {METADATA_FILE}."
        )
        logger.exception("❌ %s", msg)
        raise ReleaseScriptError(msg) from e
    else:
        logger.info(
            "✅ Found plugin '%s' version '%s' in %s",
            metadata["name"],
            metadata["version"],
            METADATA_FILE,
        )
        return metadata


def update_repository_file(metadata: PluginMetadata) -> None:
    """Update all relevant tags in the plugins.xml file from metadata.

    Args:
        metadata: A dictionary containing the plugin's core metadata.

    Raises:
        ReleaseScriptError: If plugins.xml or required tags are not found.
    """
    plugin_name = metadata["name"]
    version = metadata["version"]
    logger.info(
        "Updating %s for '%s' version %s...", PLUGINS_XML_FILE, plugin_name, version
    )

    # Ensure the 'packages' directory exists before trying to access the file.
    PLUGINS_XML_FILE.parent.mkdir(exist_ok=True)

    if not PLUGINS_XML_FILE.exists():
        msg = (
            f"Repository file not found at '{PLUGINS_XML_FILE}'. If this is the "
            "first release, please create it inside the 'packages' directory."
        )
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

        def _update_tag(parent_node: ElTr.Element, tag_name: str, value: str) -> None:  # pyright: ignore[reportAttributeAccessIssue]
            """Find and update the text of a child tag."""
            if (tag := parent_node.find(tag_name)) is not None:
                tag.text = value
            else:
                logger.warning(
                    "⚠️ Tag '%s' not found in %s. Skipping update.",
                    tag_name,
                    PLUGINS_XML_FILE,
                )

        plugin_node.set("version", version)

        # Update all relevant tags from metadata
        _update_tag(plugin_node, "description", metadata["description"])
        _update_tag(plugin_node, "about", metadata["about"])
        _update_tag(plugin_node, "version", version)
        _update_tag(
            plugin_node, "qgis_minimum_version", metadata["qgis_minimum_version"]
        )
        _update_tag(plugin_node, "author_name", metadata["author"])
        _update_tag(plugin_node, "email", metadata["email"])

        # Update file name and download URL
        new_zip_filename: str = f"{plugin_name}-{version}.zip"
        _update_tag(plugin_node, "file_name", new_zip_filename)

        new_url = f"{metadata['url_base'].rstrip('/')}/{new_zip_filename}"
        _update_tag(plugin_node, "download_url", new_url)

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
        # The root directory name inside the zip file MUST be a valid Python
        # module name (no spaces). This is read from pb_tool.cfg.
        plugin_zip_dir = config.get("plugin", "name")
        if " " in plugin_zip_dir:
            msg = (
                f"The plugin 'name' in pb_tool.cfg ('{plugin_zip_dir}') "
                "must not contain spaces. Use an underscore_ or remove them."
            )
            raise ReleaseScriptError(msg)

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
    2. Updates the repository XML in the 'packages' directory.
    3. Compiles resources and translations.
    4. Packages the plugin into a zip file in the 'packages' directory.

    Raises:
        ReleaseScriptError: If any step in the release process fails.
    """
    metadata = get_plugin_metadata()
    update_repository_file(metadata)
    # The 'shell=True' is required on Windows to run .bat files correctly
    # from the PATH. This is safe as the command is a static string.
    run_command(["compile.bat"], shell=True)  # noqa: S604

    package_plugin_from_config(metadata["name"], metadata["version"])

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
