"""Copy bundled Python and build dependency licenses next to the frozen app."""
from importlib import metadata
import os
from pathlib import Path
import re
import shutil
import sys
from urllib.request import urlopen


def package_licenses(name, destination):
    distribution = metadata.distribution(name)
    files = distribution.files or ()
    license_files = [item for item in files
                     if re.match(r"^(license|licence|copying|notice)(\.|$)",
                                 Path(str(item)).name, re.IGNORECASE)]
    target = destination / "licenses" / re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    copied = []
    for item in license_files:
        source = Path(distribution.locate_file(item))
        if not source.is_file():
            continue
        output = target / Path(str(item)).name
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
        copied.append(output.relative_to(destination).as_posix())
    if not copied:
        raise RuntimeError(f"No license files found for bundled build component {name}.")
    return copied


def python_license(destination):
    candidates = [Path(sys.base_prefix) / "LICENSE.txt",
                  Path(sys.base_prefix) / "LICENSE",
                  Path(sys.base_prefix) / "Resources/English.lproj/License.rtf",
                  Path(sys.prefix) / "LICENSE.txt",
                  Path(sys.prefix) / "LICENSE",
                  Path(sys.prefix) / "Resources/English.lproj/License.rtf"]
    source = next((path for path in candidates if path.is_file()), None)
    suffix = ".rtf" if source and source.suffix.lower() == ".rtf" else ".txt"
    output = destination / "licenses" / ("CPython-LICENSE" + suffix)
    output.parent.mkdir(parents=True, exist_ok=True)
    if source is not None:
        shutil.copyfile(source, output)
    else:
        version = ".".join(str(part) for part in sys.version_info[:3])
        url = f"https://raw.githubusercontent.com/python/cpython/v{version}/LICENSE"
        try:
            with urlopen(url, timeout=20) as response:
                license_text = response.read()
        except OSError as error:
            raise RuntimeError(f"Could not retrieve the CPython {version} license from the official source: {error}") from error
        if not license_text.strip():
            raise RuntimeError(f"The official CPython {version} license file was empty.")
        output.write_bytes(license_text)
    return output.relative_to(destination).as_posix()


def main():
    if sys.platform == "darwin" and "SSL_CERT_FILE" not in os.environ and Path("/etc/ssl/cert.pem").is_file():
        os.environ["SSL_CERT_FILE"] = "/etc/ssl/cert.pem"
    if len(sys.argv) != 2:
        raise SystemExit("usage: copy_licenses.py APP_RESOURCES_DIRECTORY")
    destination = Path(sys.argv[1])
    destination.mkdir(parents=True, exist_ok=True)

    notices = ["Third-party notices for LOD pane Word.", ""]
    python_path = python_license(destination)
    notices.append("CPython runtime: Python Software Foundation License.")
    notices.append(f"License text: {python_path}")

    for package, description in (
        ("cryptography", "Apache License 2.0 or BSD License"),
        ("cffi", "MIT License"),
        ("PyInstaller", "GPLv2 with the PyInstaller bootloader exception"),
    ):
        copied = package_licenses(package, destination)
        notices.extend(["", f"{package}: {description}.",
                        "License text: " + ", ".join(copied)])

    (destination / "THIRD-PARTY-NOTICES.txt").write_text(
        "\n".join(notices) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
