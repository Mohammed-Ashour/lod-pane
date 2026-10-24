"""Build the LibreOffice OXT and Word manifest using only Python's standard library."""
from pathlib import Path
import struct
import zlib
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"


def icon(size=80):
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            left, right, middle = size // 5, size * 4 // 5, size // 2
            top, bottom, stroke = size // 5, size * 3 // 4, max(1, size // 40)
            paper = (left <= x < middle - stroke or middle + stroke <= x <= right) and top <= y <= bottom
            line = paper and (y < top + stroke or y > bottom - stroke or x < left + stroke or x > right - stroke or middle - 2 * stroke <= x < middle + 2 * stroke)
            row.extend((255, 255, 255) if line else (20, 127, 156))
        rows.append(b"\0" + row)
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")


def main():
    DIST.mkdir(exist_ok=True)
    image = icon()
    (ROOT / "word/icon.png").write_bytes(image)
    files = {
        "panel.py": (ROOT / "libreoffice/panel.py").read_bytes(),
        "pythonpath/lodpane.py": (ROOT / "lodpane.py").read_bytes(),
        "sidebar-icon.png": icon(24),
        "description.xml": b'''<?xml version="1.0" encoding="UTF-8"?>
<description xmlns="http://openoffice.org/extensions/description/2006" xmlns:xlink="http://www.w3.org/1999/xlink">
<identifier value="org.lodpane.Notebook"/><version value="0.7.0"/>
<display-name><name lang="en">LOD pane</name></display-name>
<dependencies><LibreOffice-minimal-version xmlns="http://libreoffice.org/extensions/description/2011" value="7.4"/></dependencies>
</description>''',
        "panel.component": b'''<?xml version="1.0" encoding="UTF-8"?>
<components xmlns="http://openoffice.org/2010/uno-components"><component loader="com.sun.star.loader.Python" uri="./panel.py"><implementation name="org.lodpane.PanelFactory"><service name="org.lodpane.PanelFactory"/></implementation></component></components>''',
        "Factory.xcu": b'''<?xml version="1.0" encoding="UTF-8"?>
<oor:component-data xmlns:oor="http://openoffice.org/2001/registry" oor:name="Factories" oor:package="org.openoffice.Office.UI"><node oor:name="Registered"><node oor:name="UIElementFactories"><node oor:name="org.lodpane.Factory" oor:op="replace"><prop oor:name="Type"><value>toolpanel</value></prop><prop oor:name="Name"><value>LODPane</value></prop><prop oor:name="Module"><value/></prop><prop oor:name="FactoryImplementation"><value>org.lodpane.PanelFactory</value></prop></node></node></node></oor:component-data>''',
        "Sidebar.xcu": b'''<?xml version="1.0" encoding="UTF-8"?>
<oor:component-data xmlns:oor="http://openoffice.org/2001/registry" oor:name="Sidebar" oor:package="org.openoffice.Office.UI"><node oor:name="Content">
<node oor:name="DeckList"><node oor:name="LODPaneDeck" oor:op="replace"><prop oor:name="Title"><value xml:lang="en-US">LOD pane</value></prop><prop oor:name="Id"><value>LODPaneDeck</value></prop><prop oor:name="IconURL"><value>vnd.sun.star.extension://org.lodpane.Notebook/sidebar-icon.png</value></prop><prop oor:name="ContextList"><value oor:separator=";">Writer, any, visible</value></prop><prop oor:name="OrderIndex"><value>900</value></prop></node></node>
<node oor:name="PanelList"><node oor:name="LODPaneNotebook" oor:op="replace"><prop oor:name="Title"><value xml:lang="en-US">Open notebook</value></prop><prop oor:name="Id"><value>LODPaneNotebook</value></prop><prop oor:name="DeckId"><value>LODPaneDeck</value></prop><prop oor:name="ContextList"><value oor:separator=";">Writer, any, visible</value></prop><prop oor:name="ImplementationURL"><value>private:resource/toolpanel/LODPane/Notebook</value></prop><prop oor:name="TitleBarIsOptional"><value>true</value></prop><prop oor:name="ShowForReadOnlyDocument"><value>true</value></prop></node></node>
</node></oor:component-data>''',
        "META-INF/manifest.xml": b'''<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="http://openoffice.org/2001/manifest"><manifest:file-entry manifest:media-type="application/vnd.sun.star.uno-components" manifest:full-path="panel.component"/><manifest:file-entry manifest:media-type="application/vnd.sun.star.configuration-data" manifest:full-path="Factory.xcu"/><manifest:file-entry manifest:media-type="application/vnd.sun.star.configuration-data" manifest:full-path="Sidebar.xcu"/></manifest:manifest>'''
    }
    with ZipFile(DIST / "lod-pane.oxt", "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    manifest = '''<?xml version="1.0" encoding="UTF-8"?>
<OfficeApp xmlns="http://schemas.microsoft.com/office/appforoffice/1.1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="TaskPaneApp">
  <Id>ad0b38c2-5f64-4d1e-9978-a1ea27d53814</Id><Version>1.1.0.0</Version>
  <ProviderName>LOD pane</ProviderName><DefaultLocale>en-US</DefaultLocale>
  <DisplayName DefaultValue="LOD pane"/><Description DefaultValue="Look up Luxembourgish words, save vocabulary, and explicitly replace selected text after preview." />
  <IconUrl DefaultValue="https://localhost:43127/icon.png"/>
  <SupportUrl DefaultValue="https://localhost:43127/help"/>
  <AppDomains><AppDomain>https://localhost:43127</AppDomain></AppDomains>
  <Hosts><Host Name="Document"/></Hosts>
  <Requirements><Sets DefaultMinVersion="1.3"><Set Name="WordApi"/></Sets></Requirements>
  <DefaultSettings><SourceLocation DefaultValue="https://localhost:43127/word.html"/></DefaultSettings>
  <Permissions>ReadWriteDocument</Permissions>
</OfficeApp>
'''
    (DIST / "word-manifest.xml").write_text(manifest, encoding="utf-8")
    launcher = DIST / "start-word.command"
    launcher.write_text('#!/bin/sh\ncd -- "$(dirname -- "$0")/.."\nexport PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"\npython3 server.py\nprintf "Press Return to close this window."\nread answer\n', encoding="utf-8")
    launcher.chmod(0o755)
    (DIST / "start-word.cmd").write_text('@echo off\r\ncd /d "%~dp0.."\r\npy -3 server.py\r\npause\r\n', encoding="utf-8")
    print("Built dist/lod-pane.oxt, dist/word-manifest.xml, and Word companion launchers.")


if __name__ == "__main__":
    main()
