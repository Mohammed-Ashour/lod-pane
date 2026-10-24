"""Check native certificate and registration boundaries without modifying OS settings."""
import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import native_word as native
from cryptography import x509
from cryptography.hazmat.primitives import hashes


def run():
    with TemporaryDirectory(prefix="lod-native-cert-test-") as temporary:
        directory = Path(temporary)
        native.certificates(directory)
        folder = directory / "certificates"
        assert {path.name for path in folder.iterdir()} == {"ca.crt", "localhost.crt", "localhost.key"}
        ca = x509.load_pem_x509_certificate((folder / "ca.crt").read_bytes())
        leaf = x509.load_pem_x509_certificate((folder / "localhost.crt").read_bytes())
        assert ca.subject == leaf.issuer
        assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.path_length == 0
        assert leaf.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False
        assert "localhost" in leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
        digest = ca.fingerprint(hashes.SHA256())
        native.certificates(directory)
        assert x509.load_pem_x509_certificate((folder / "ca.crt").read_bytes()).fingerprint(hashes.SHA256()) == digest
        other = directory / "other"
        native.certificates(other)
        assert (other / "certificates/ca.crt").read_bytes() != (folder / "ca.crt").read_bytes()

        # Mac registration copies the generated manifest and respects a later user edit.
        with patch.object(native.sys, "platform", "darwin"), patch.object(native.Path, "home", return_value=directory):
            native.register_manifest(directory, True)
            target = directory / "Library/Containers/com.microsoft.Word/Data/Documents/wef/lod-pane.xml"
            assert target.read_bytes() == (ROOT / "dist/word-manifest.xml").read_bytes()
            target.write_text("user-managed replacement")
            native.register_manifest(directory, False)
            assert target.read_text() == "user-managed replacement"

        # Frozen lifecycle commands use the packaged executable and the private CA.
        with patch.object(native.manager.sys, "frozen", True, create=True), \
             patch.object(native.manager.sys, "_MEIPASS", str(ROOT), create=True):
            assert native.manager.command(directory) == [sys.executable, "run", "--install-dir", str(directory)]
            class Response:
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def read(self): return (ROOT / "word/index.html").read_bytes()
            with patch.object(native.manager.ssl, "create_default_context") as tls, \
                 patch.object(native.manager, "urlopen", return_value=Response()), \
                 patch.object(native.manager, "running", return_value=True):
                native.manager.wait_ready(directory)
                tls.assert_called_once_with(cafile=str(folder / "ca.crt"))

        failed = directory / "failed-install"
        with patch.object(native, "registration_snapshot", return_value=None), \
             patch.object(native, "restore_registration") as restore, \
             patch.object(native, "register_manifest") as register, \
             patch.object(native, "trust_ca") as trust, \
             patch.object(native.manager, "startup_enabled", return_value=False), \
             patch.object(native.manager, "running", return_value=False), \
             patch.object(native.manager, "stop"), \
             patch.object(native.manager, "login_startup"), \
             patch.object(native.manager, "start", side_effect=RuntimeError("port occupied")):
            try:
                native.install(failed)
                raise AssertionError("startup failure hidden")
            except RuntimeError as error:
                assert "port occupied" in str(error)
            register.assert_called_once_with(failed, True)
            restore.assert_called_once_with(None)
            assert [call.args[1] for call in trust.call_args_list] == [True, False]
            assert not (failed / "native-installed").exists()
            assert not (failed / "certificates/ca.crt").exists()

    print("PASS: unique native CA/leaf generation, CA private-key disposal, reuse, manifest ownership, and frozen lifecycle/TLS paths.")


if __name__ == "__main__":
    run()
