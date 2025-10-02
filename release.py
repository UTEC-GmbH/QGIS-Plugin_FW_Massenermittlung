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
from xml.etree.ElementTree import Element, ElementTree, SubElement

from defusedxml import ElementTree as DefET

# --- Configuration ---
METADATA_FILE: Path = Path("metadata.txt")


# --- Logger ---
logger: logging.Logger = logging.getLogger(__name__)


class PluginMetadata(TypedDict):
    """A dictionary representing the plugin's metadata."""

    name: str
    version: str
    url_base: str
    description: str
    changelog: str
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
            "changelog": config.get("general", "changelog"),
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
    """Update the master plugins.xml file directly in the shared repository.

    This function implements a fully automated, multi-plugin-safe workflow:
    1. It locates the shared repository from the metadata.
    2. It checks for write permissions to that directory.
    3. It reads the master plugins.xml (or creates a new one in memory if none
       exists).
    4. It updates or adds the entry for the current plugin.
    5. It writes the result directly back to the shared repository.

    Args:
        metadata: A dictionary containing the plugin's core metadata.

    Raises:
        ReleaseScriptError: If the shared repository is not accessible or the XML
                            file cannot be parsed.
    """
    plugin_name = metadata["name"]
    version = metadata["version"]
    logger.info("Updating repository file for '%s' version %s...", plugin_name, version)

    # --- Step 1: Locate repository and check permissions ---
    # Derive the filesystem path from the file:// URL in metadata.
    # This works for UNC paths (e.g., "file:////server/share") on Windows.
    url_base = metadata["url_base"]
    if not url_base.startswith("file://"):
        msg = (
            f"Cannot determine shared repository path. The 'download_url_base' "
            f"in {METADATA_FILE} must be a 'file://' URL, but it is '{url_base}'."
        )
        raise ReleaseScriptError(msg)

    # The `removeprefix` method cleanly strips "file://" to get the path.
    # `pathlib.Path` on Windows correctly interprets "//server/share" as a UNC path.
    shared_repo_path = Path(url_base.removeprefix("file://"))
    master_xml_path = shared_repo_path / "plugins.xml"

    # Ensure the shared repository directory exists and is writable.
    try:
        shared_repo_path.mkdir(parents=True, exist_ok=True)
        if not os.access(shared_repo_path, os.W_OK):
            msg: str = (
                f"No write permission for the shared repository: {shared_repo_path}. "
                "Please check permissions or run as a user with access."
            )
            raise ReleaseScriptError(msg)
    except OSError as e:
        msg = f"Could not access or create shared repository directory: {e}"
        raise ReleaseScriptError(msg) from e

    # --- Step 2: Read or create the XML tree ---
    if master_xml_path.exists():
        logger.info("Reading master repository file: %s", master_xml_path)
        try:
            tree: ElementTree = DefET.parse(master_xml_path)
            root: Element = tree.getroot()  # pyright: ignore[reportAssignmentType]
        except DefET.ParseError as e:
            msg = f"Error parsing {master_xml_path}."
            logger.exception("❌ %s", msg)
            raise ReleaseScriptError(msg) from e
    else:
        logger.warning(
            "⚠️ Master repository file not found at '%s'. "
            "This is expected if it's the first plugin release.",
            master_xml_path,
        )
        logger.info("Creating a new XML structure in memory.")
        root = Element("plugins")
        tree = ElementTree(root)

    # --- Step 3: Find existing entry or create a new one ---
    try:
        plugin_node: Element[str] | None = next(
            (
                node
                for node in root.findall("pyqgis_plugin")
                if node.get("name") == plugin_name
            ),
            None,
        )

        if plugin_node is None:
            logger.info("Plugin '%s' not found. Creating new entry.", plugin_name)
            plugin_node = SubElement(root, "pyqgis_plugin", name=plugin_name)
            # Pre-populate essential child tags so _update_tag finds them
            for tag in [
                "version",
                "changelog",
                "description",
                "qgis_minimum_version",
                "author_name",
                "email",
                "file_name",
                "download_url",
            ]:
                SubElement(plugin_node, tag)
        else:
            logger.info("Found existing entry for '%s'. Updating...", plugin_name)

        def _update_xml_tag(parent_node: Element, tag_name: str, value: str) -> None:
            """Find and update the text of a child tag."""
            if (tag := parent_node.find(tag_name)) is not None:
                tag.text = value
            else:
                logger.warning(
                    "⚠️ Tag '%s' not found in %s. Skipping update.",
                    tag_name,
                    master_xml_path,
                )

        # --- Step 4: Update all tags from metadata ---
        plugin_node.set("version", version)

        _update_xml_tag(plugin_node, "version", version)
        _update_xml_tag(plugin_node, "description", metadata["description"])
        _update_xml_tag(plugin_node, "changelog", metadata["changelog"])
        _update_xml_tag(
            plugin_node, "qgis_minimum_version", metadata["qgis_minimum_version"]
        )
        _update_xml_tag(plugin_node, "author_name", metadata["author"])
        _update_xml_tag(plugin_node, "email", metadata["email"])

        clean_plugin_name: str = plugin_name.replace(" ", "_")
        new_zip_filename: str = f"{clean_plugin_name}.zip"
        _update_xml_tag(plugin_node, "file_name", new_zip_filename)

        new_url = f"{metadata['url_base'].rstrip('/')}/{new_zip_filename}"
        _update_xml_tag(plugin_node, "download_url", new_url)

        tree.write(master_xml_path, encoding="utf-8", xml_declaration=True)
        logger.info("✅ Successfully updated repository file: %s", master_xml_path)

    except DefET.ParseError as e:
        msg = f"Error parsing {master_xml_path}."
        logger.exception("❌ %s", msg)
        raise ReleaseScriptError(msg) from e


def run_command(command: list[str], shell: bool = False) -> None:
    """Run a command in a subprocess and checks for errors."""
    logger.info("\n▶️ Running command: %s", " ".join(command))
    try:
        env: dict[str, str] = os.environ.copy()

        python_bin_dir = str(Path(sys.executable).parent)
        if "PATH" in env:
            # os.pathsep is ';' on Windows and ':' on Linux/macOS
            if python_bin_dir not in env["PATH"].split(os.pathsep):
                env["PATH"] = f"{python_bin_dir}{os.pathsep}{env['PATH']}"
        else:
            env["PATH"] = python_bin_dir

        result: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603
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


def package_plugin_directly(metadata: PluginMetadata) -> None:
    """Create a zip archive of the plugin directly in the shared repository.

    This function reads packaging configuration from 'pb_tool.cfg', collects
    the specified files and directories, and creates a zip archive in the
    shared repository.

    Args:
        metadata: The plugin's metadata, used to determine the output path
                  and zip file name.

    Raises:
        ReleaseScriptError: If 'pb_tool.cfg' is not found or is invalid.
    """
    plugin_name = metadata["name"]
    clean_plugin_name: str = plugin_name.replace(" ", "_")
    logger.info("\n▶️ Packaging '%s'...", plugin_name)

    pb_tool_cfg_path = Path("pb_tool.cfg")
    if not pb_tool_cfg_path.exists():
        msg = f"Configuration file not found at '{pb_tool_cfg_path}'"
        raise ReleaseScriptError(msg)

    config = configparser.ConfigParser()
    config.read(pb_tool_cfg_path)

    try:
        # The root directory name inside the zip file MUST be a valid Python
        # module name. This is read from pb_tool.cfg.
        plugin_zip_dir = config.get("plugin", "name")

        # Validate that the directory name in the zip matches the sanitized
        # name from metadata.txt. This is crucial for QGIS to find the plugin.
        if plugin_zip_dir != clean_plugin_name:
            msg = (
                f"Name mismatch: The 'name' in 'pb_tool.cfg' ('{plugin_zip_dir}') "
                f"must match the 'name' from 'metadata.txt' with spaces replaced "
                f"by underscores ('{clean_plugin_name}')."
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

        # --- Create a clean metadata.txt in memory for packaging ---
        # This ensures the released plugin doesn't identify as "(dev)"
        original_metadata_path = Path("metadata.txt")
        with open(original_metadata_path, encoding="utf-8") as f:
            original_content = f.read()

        lines = original_content.splitlines(True)
        new_lines = []
        replaced = False
        for line in lines:
            if not replaced and line.strip().startswith("name="):
                new_lines.append(f"name={plugin_name}\n")
                replaced = True
            else:
                new_lines.append(line)
        clean_metadata_content = "".join(new_lines)

        # --- Create the zip archive ---
        shared_repo_path = Path(metadata["url_base"].removeprefix("file://"))
        zip_path = shared_repo_path / f"{clean_plugin_name}.zip"
        logger.info("Creating zip archive at: %s", zip_path)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            # Add specified individual files
            for file_str in files_to_zip:
                # Intercept metadata.txt to write the cleaned version
                if file_str == "metadata.txt":
                    arcname = Path(plugin_zip_dir) / "metadata.txt"
                    zipf.writestr(str(arcname), clean_metadata_content.encode("utf-8"))
                    logger.info("Writing cleaned metadata.txt to zip archive.")
                    continue

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

        logger.info(
            "✅ Successfully created plugin package in shared repository: %s", zip_path
        )

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
    2. Updates the repository XML directly on the shared drive.
    3. Compiles resources and translations.
    4. Packages the plugin into a zip file directly on the shared drive.

    Raises:
        ReleaseScriptError: If any step in the release process fails.
    """
    metadata = get_plugin_metadata()
    original_name = metadata["name"]
    release_name = original_name.replace("(dev)", "").strip()

    if not release_name:
        msg = "Plugin name cannot be empty after removing '(dev)' marker."
        raise ReleaseScriptError(msg)

    if original_name != release_name:
        logger.info(
            "Note: Development marker '(dev)' found. Releasing with clean name: '%s'",
            release_name,
        )
        metadata["name"] = release_name

    update_repository_file(metadata)
    # The 'shell=True' is required on Windows to run .bat files correctly
    # from the PATH. This is safe as the command is a static string.
    run_command(["compile.bat"], shell=True)  # noqa: S604

    package_plugin_directly(metadata)

    logger.info("\n🎉 --- Release process complete! --- 🎉")
    shared_repo_path = Path(metadata["url_base"].removeprefix("file://"))
    logger.info(
        "✅ Plugin successfully released directly to the shared repository: %s",
        shared_repo_path,
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
