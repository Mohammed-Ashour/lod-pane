"""Build and verify a macOS PKG that explicitly upgrades the owned app bundle."""
import argparse
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "dist"


def package(app_path, output_path, package_identifier, bundle_identifier):
    info_path = app_path / "Contents/Info.plist"
    info = plistlib.loads(info_path.read_bytes())
    metadata = json.loads((DIST / "native-build-info.json").read_text(encoding="utf-8"))
    if info.get("CFBundleIdentifier") != bundle_identifier:
        raise RuntimeError(f"Unexpected app bundle identifier in {info_path}.")
    if info.get("CFBundleVersion") != metadata["bundle_version"]:
        raise RuntimeError("App CFBundleVersion does not match native build metadata.")
    if info.get("CFBundleShortVersionString") != metadata["marketing_version"]:
        raise RuntimeError("App marketing version does not match native build metadata.")
    if info.get("LODPaneBuildCommit") != metadata["commit_sha"]:
        raise RuntimeError("App build commit does not match native build metadata.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lod-native-pkg-", dir=DIST) as temporary:
        temporary = Path(temporary)
        root = temporary / "root"
        bundle_relative = Path("Applications") / app_path.name
        staged_app = root / bundle_relative
        staged_app.parent.mkdir(parents=True)
        shutil.copytree(app_path, staged_app, symlinks=True)
        component_info = [{
            "RootRelativeBundlePath": bundle_relative.as_posix(),
            "BundleIsRelocatable": False,
            "BundleIsVersionChecked": False,
            "BundleHasStrictIdentifier": True,
            "BundleOverwriteAction": "upgrade",
        }]
        component_plist = temporary / "components.plist"
        with component_plist.open("wb") as handle:
            plistlib.dump(component_info, handle)

        subprocess.run([
            "pkgbuild", "--root", str(root),
            "--component-plist", str(component_plist),
            "--identifier", package_identifier,
            "--version", metadata["bundle_version"],
            "--install-location", "/",
            str(output_path),
        ], check=True)

        expanded = temporary / "expanded"
        subprocess.run(["pkgutil", "--expand", str(output_path), str(expanded)], check=True)
        package_info = ET.parse(expanded / "PackageInfo").getroot()
        if package_info.attrib.get("identifier") != package_identifier:
            raise RuntimeError("Expanded PackageInfo has the wrong package identifier.")
        if package_info.attrib.get("version") != metadata["bundle_version"]:
            raise RuntimeError("Expanded PackageInfo has the wrong monotonic version.")
        if package_info.attrib.get("install-location") != "/":
            raise RuntimeError("Expanded PackageInfo does not install from the filesystem root.")
        if package_info.attrib.get("relocatable") != "false":
            raise RuntimeError("Expanded PackageInfo must disable bundle relocation.")

        bundles = [node for node in package_info.findall("bundle")
                   if node.attrib.get("id") == bundle_identifier]
        if len(bundles) != 1:
            raise RuntimeError("Expanded PackageInfo must own exactly one matching app bundle.")
        path = bundles[0].attrib.get("path", "").lstrip("./")
        if path != bundle_relative.as_posix():
            raise RuntimeError("Expanded PackageInfo points at an unexpected app bundle path.")
        if bundles[0].attrib.get("CFBundleVersion") != metadata["bundle_version"]:
            raise RuntimeError("Expanded PackageInfo bundle version does not match build metadata.")
        if bundles[0].attrib.get("CFBundleShortVersionString") != metadata["marketing_version"]:
            raise RuntimeError("Expanded PackageInfo marketing version does not match build metadata.")

        upgrade = package_info.find("upgrade-bundle")
        if upgrade is None or not any(node.attrib.get("id") == bundle_identifier
                                      for node in upgrade.findall("bundle")):
            raise RuntimeError("Expanded PackageInfo does not mark the app bundle for upgrade.")
        relocate = package_info.find("relocate")
        if relocate is not None and any(node.attrib.get("id") == bundle_identifier
                                        for node in relocate.findall("bundle")):
            raise RuntimeError("Expanded PackageInfo unexpectedly marks an app bundle relocatable.")
        print(f"Verified {output_path.name}: {bundle_identifier} {metadata['bundle_version']} upgrade, fixed path.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package-identifier", required=True)
    parser.add_argument("--bundle-identifier", required=True)
    args = parser.parse_args()
    package(args.app.resolve(), args.output.resolve(), args.package_identifier, args.bundle_identifier)


if __name__ == "__main__":
    main()
