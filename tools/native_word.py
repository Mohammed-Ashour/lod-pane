"""Bundled Word companion: first-run setup, native management and background service."""
import argparse
from datetime import datetime, timedelta, timezone
import ipaddress
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
from tempfile import TemporaryDirectory, gettempdir
import time
from urllib.request import urlopen

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

import install_word as manager
import server

ADDIN_ID = "ad0b38c2-5f64-4d1e-9978-a1ea27d53814"
DEVELOPER_KEY = r"Software\Microsoft\Office\16.0\WEF\Developer"


def configure_tls():
    # A frozen macOS Python must not depend on the build machine's Python CA path.
    # Honor an administrator-provided CA bundle; otherwise use macOS's system bundle.
    system_ca = Path("/etc/ssl/cert.pem")
    if sys.platform == "darwin" and "SSL_CERT_FILE" not in os.environ and system_ca.is_file():
        os.environ["SSL_CERT_FILE"] = str(system_ca)


def resources():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def dialog(message, question=False):
    """Native OS prompt; never display a dialog in a background process."""
    if sys.platform == "win32":
        import ctypes
        flags = 0x24 if question else 0x40  # Yes/No + question, or OK + information
        return ctypes.windll.user32.MessageBoxW(None, message, "LOD pane Word", flags) == 6
    # Pass content as an argument rather than interpolating AppleScript source.
    script = ('on run argv\nset msg to item 1 of argv\n'
              'display dialog msg with title "LOD pane Word" buttons ' +
              ('{"Cancel", "Continue"} default button "Continue"' if question else '{"OK"} default button "OK"') +
              '\nend run')
    result = subprocess.run(["osascript", "-e", script, message], capture_output=True, text=True)
    if result.returncode and "(-128)" not in result.stderr:
        raise RuntimeError("Could not show setup dialog: " + result.stderr.strip())
    return result.returncode == 0


def management_action(active):
    toggle = "Stop" if active else "Start"
    if sys.platform == "win32":
        import ctypes
        answer = ctypes.windll.user32.MessageBoxW(None,
            "The companion is " + ("running." if active else "stopped.") +
            "\nYes: " + toggle + " companion\nNo: Uninstall Word integration\nCancel: Close",
            "LOD pane Word", 0x23)
        return {6: toggle.lower(), 7: "uninstall"}.get(answer)
    script = ('on run argv\nset picked to button returned of (display dialog '
              '"Manage the local Word companion." with title "LOD pane Word" '
              'buttons {"Close", "Uninstall", item 1 of argv} default button (item 1 of argv))\n'
              'return picked\nend run')
    result = subprocess.run(["osascript", "-e", script, toggle], capture_output=True, text=True, check=True)
    return {toggle: toggle.lower(), "Uninstall": "uninstall"}.get(result.stdout.strip())


def certificates(directory):
    """Create a unique local CA and TLS leaf. The CA private key is never saved."""
    folder = directory / "certificates"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    paths = [folder / name for name in ("ca.crt", "localhost.crt", "localhost.key")]
    if all(path.is_file() for path in paths):
        leaf = x509.load_pem_x509_certificate(paths[1].read_bytes())
        if leaf.not_valid_after_utc > datetime.now(timezone.utc) + timedelta(days=7):
            return
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "LOD pane local companion")])
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=3650))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
              key_encipherment=False, data_encipherment=False, key_agreement=False,
              key_cert_sign=True, crl_sign=True, encipher_only=None, decipher_only=None), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
            .issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                key_encipherment=True, data_encipherment=False, key_agreement=False,
                key_cert_sign=False, crl_sign=False, encipher_only=None, decipher_only=None), critical=True)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    # If renewing, keep the old public CA so uninstall can remove its exact trust entry.
    if paths[0].exists():
        old = x509.load_pem_x509_certificate(paths[0].read_bytes())
        shutil.copy2(paths[0], folder / (old.fingerprint(hashes.SHA1()).hex() + ".old-ca.crt"))
    paths[0].write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    paths[1].write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    paths[2].write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    paths[2].chmod(0o600)


def trust_ca(path, enable):
    ca = x509.load_pem_x509_certificate(path.read_bytes())
    thumbprint = ca.fingerprint(hashes.SHA1()).hex()
    if sys.platform == "win32":
        if not enable:
            query = subprocess.run(["certutil", "-user", "-store", "Root", thumbprint], capture_output=True, text=True)
            if query.returncode:
                if "0x80092004" in (query.stdout + query.stderr).lower():
                    return  # Already absent, including after a repeated uninstall.
                query.check_returncode()
        args = ["certutil", "-user", "-addstore", "Root", str(path)] if enable else ["certutil", "-user", "-delstore", "Root", thumbprint]
    else:
        keychain = str(Path.home() / "Library/Keychains/login.keychain-db")
        if not enable:
            query = subprocess.run(["security", "find-certificate", "-a", "-Z", keychain], capture_output=True, text=True)
            if query.returncode not in (0, 44):
                query.check_returncode()
            if thumbprint.upper() not in query.stdout.upper():
                return
        args = (["security", "add-trusted-cert", "-r", "trustRoot", "-k", keychain, str(path)] if enable
                else ["security", "delete-certificate", "-Z", thumbprint, keychain])
    subprocess.run(args, check=True, capture_output=True)


def register_manifest(directory, enable):
    manifest = directory / "word-manifest.xml"
    if enable:
        shutil.copy2(resources() / "dist/word-manifest.xml", manifest)
    if sys.platform == "win32":
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, DEVELOPER_KEY) as key:
            if enable:
                winreg.SetValueEx(key, ADDIN_ID, 0, winreg.REG_SZ, str(manifest))
            else:
                try:
                    if winreg.QueryValueEx(key, ADDIN_ID)[0] == str(manifest):
                        winreg.DeleteValue(key, ADDIN_ID)
                except FileNotFoundError:
                    pass
    else:
        target = Path.home() / "Library/Containers/com.microsoft.Word/Data/Documents/wef/lod-pane.xml"
        if enable:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(manifest, target)
        elif target.is_file() and manifest.is_file() and target.read_bytes() == manifest.read_bytes():
            target.unlink()
    if not enable:
        manifest.unlink(missing_ok=True)


def registration_snapshot():
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DEVELOPER_KEY) as key:
                return winreg.QueryValueEx(key, ADDIN_ID)[0]
        except FileNotFoundError:
            return None
    target = Path.home() / "Library/Containers/com.microsoft.Word/Data/Documents/wef/lod-pane.xml"
    return target.read_bytes() if target.is_file() else None


def restore_registration(state):
    if sys.platform == "win32":
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, DEVELOPER_KEY) as key:
            if state is None:
                try:
                    winreg.DeleteValue(key, ADDIN_ID)
                except FileNotFoundError:
                    pass
            else:
                winreg.SetValueEx(key, ADDIN_ID, 0, winreg.REG_SZ, state)
    else:
        target = Path.home() / "Library/Containers/com.microsoft.Word/Data/Documents/wef/lod-pane.xml"
        if state is None:
            target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(state)


def install(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = directory / "native-installed"
    prior_marker = marker.read_bytes() if marker.is_file() else None
    prior_registration = registration_snapshot()
    prior_manifest = (directory / "word-manifest.xml").read_bytes() if (directory / "word-manifest.xml").is_file() else None
    prior_certificates = {name: (directory / "certificates" / name).read_bytes()
                          for name in ("ca.crt", "localhost.crt", "localhost.key")
                          if (directory / "certificates" / name).is_file()}
    was_enabled, was_running = manager.startup_enabled(), manager.running(directory)
    # A cancelled trust prompt or failed setup must offer setup again on next launch.
    marker.unlink(missing_ok=True)
    trusted = False
    try:
        manager.stop(directory)
        manager.login_startup(directory, False)
        certificates(directory)
        trust_ca(directory / "certificates/ca.crt", True)
        trusted = True
        register_manifest(directory, True)
        manager.login_startup(directory, True)
        manager.start(directory)
    except Exception:
        manager.login_startup(directory, False)
        manager.stop(directory)
        restore_registration(prior_registration)
        if trusted and (prior_marker is None or prior_certificates.get("ca.crt") != (directory / "certificates/ca.crt").read_bytes()):
            trust_ca(directory / "certificates/ca.crt", False)
        if prior_manifest is None:
            (directory / "word-manifest.xml").unlink(missing_ok=True)
        else:
            (directory / "word-manifest.xml").write_bytes(prior_manifest)
        for name in ("ca.crt", "localhost.crt", "localhost.key"):
            path = directory / "certificates" / name
            if name in prior_certificates:
                path.write_bytes(prior_certificates[name])
            else:
                path.unlink(missing_ok=True)
        manager.login_startup(directory, was_enabled)
        if was_running:
            manager.start(directory)
        else:
            manager.stop(directory)
        if prior_marker is not None:
            marker.write_bytes(prior_marker)
        raise
    marker.write_text(sys.executable, encoding="utf-8")


def uninstall(directory):
    manager.login_startup(directory, False)
    manager.stop(directory)
    register_manifest(directory, False)
    for path in (directory / "certificates").glob("*ca.crt"):
        trust_ca(path, False)
    (directory / "native-installed").unlink(missing_ok=True)
    # Retain vocabulary, logs and certificates on disk. The Windows uninstaller
    # removes program files; on macOS the user can remove the app after cleanup.


def serve(directory):
    sys.argv = [sys.argv[0], "--cert", str(directory / "certificates/localhost.crt"),
                "--key", str(directory / "certificates/localhost.key")]
    server.main()


def self_test():
    """Exercise the frozen runtime and real TLS without changing OS trust/settings."""
    assert ssl.create_default_context().cert_store_stats()["x509_ca"] > 0, "No trusted roots for LOD HTTPS"
    with TemporaryDirectory(prefix="lod-native-package-") as temporary:
        directory = Path(temporary)
        certificates(directory)
        ca = x509.load_pem_x509_certificate((directory / "certificates/ca.crt").read_bytes())
        leaf = x509.load_pem_x509_certificate((directory / "certificates/localhost.crt").read_bytes())
        assert ca.subject == leaf.issuer
        assert not any(path.name == "ca.key" for path in directory.rglob("*"))
        # A dedicated test process uses the same production server and frozen imports.
        env = dict(os.environ, LOD_PANE_DATA_DIR=str(directory / "vocabulary"))
        with (directory / "test.log").open("wb") as log:
            child = subprocess.Popen([sys.executable, "serve", "--install-dir", str(directory)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=env)
            try:
                context = ssl.create_default_context(cafile=str(directory / "certificates/ca.crt"))
                deadline = time.monotonic() + 15
                while True:
                    try:
                        with urlopen("https://localhost:43127/word.html", context=context, timeout=1) as response:
                            assert response.read() == (resources() / "word/index.html").read_bytes()
                        break
                    except OSError:
                        if time.monotonic() > deadline or child.poll() is not None:
                            raise RuntimeError("Frozen TLS smoke failed: " + (directory / "test.log").read_text(errors="replace"))
                        time.sleep(0.2)
                with urlopen("https://localhost:43127/help", context=context, timeout=2) as response:
                    assert b"Setup" in response.read()
            finally:
                child.terminate()
                child.wait(timeout=10)
    return 0


def main():
    configure_tls()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=("install", "start", "stop", "status", "uninstall", "run", "serve"))
    parser.add_argument("--install-dir", type=Path, default=manager.default_directory())
    parser.add_argument("--no-dialog", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    directory = args.install_dir.expanduser().resolve()
    if args.self_test:
        directory = Path(gettempdir()) / "lod-native-smoke-diagnostics"
    silent = args.no_dialog or args.action in ("run", "serve") or args.self_test
    try:
        if args.self_test:
            return self_test()
        action = args.action
        if action is None:
            needs_setup = not (directory / "native-installed").is_file()
            if not needs_setup:
                try:
                    leaf = x509.load_pem_x509_certificate((directory / "certificates/localhost.crt").read_bytes())
                    needs_setup = leaf.not_valid_after_utc < datetime.now(timezone.utc) + timedelta(days=7)
                    needs_setup |= (directory / "native-installed").read_text(encoding="utf-8") != sys.executable
                except (OSError, ValueError):
                    needs_setup = True
            if needs_setup:
                action = "install"
            else:
                action = management_action(manager.running(directory))
                if action is None:
                    return 0
        if action == "serve":
            serve(directory)
        elif action == "run":
            manager.run_background(directory)
        else:
            with manager.instance_lock(directory, "management.lock") as acquired:
                if not acquired:
                    raise RuntimeError("Another setup/start/stop operation is in progress.")
                if action == "install":
                    if not silent and not dialog("Install LOD pane for Word?\n\nThis trusts a certificate for the local HTTPS companion, registers the Word add-in, and starts a background companion at sign-in. Your vocabulary stays local. Close Word before continuing.", question=True):
                        return 1
                    install(directory)
                elif action == "uninstall":
                    if not silent and not dialog("Remove Word registration, login startup and this companion's local certificate trust? Vocabulary is retained.", question=True):
                        return 1
                    uninstall(directory)
                elif action == "status":
                    if not manager.running(directory):
                        raise RuntimeError("Companion is stopped.")
                    manager.wait_ready(directory)
                else:
                    {"start": manager.start, "stop": manager.stop}[action](directory)
            if not silent:
                dialog("LOD pane: " + action + " completed.\nRestart Word after setup, then open Home > Add-ins > LOD pane.\nData and logs: " + str(directory))
        return 0
    except Exception as error:
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "companion.log").open("a", encoding="utf-8") as log:
            log.write(str(error) + "\n")
        if not silent:
            dialog("LOD pane could not complete setup.\n" + str(error) + "\nDetails: " + str(directory / "companion.log"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
