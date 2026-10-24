"""Smoke-test the real UNO panel inside LibreOffice, using an isolated profile.

Run: python3 tests/libreoffice-runtime.py [--soffice /path/to/soffice]
This bypasses CLI extension-registration helpers, not OS security. It loads the
factory in LibreOffice's own Python process and uses a disposable Writer document.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
from tempfile import TemporaryDirectory
from xml.sax.saxutils import escape
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
MACOS_SOFFICE = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_soffice = MACOS_SOFFICE if MACOS_SOFFICE.is_file() else shutil.which("soffice") or MACOS_SOFFICE
    parser.add_argument("--soffice", default=str(default_soffice))
    args = parser.parse_args()
    if not Path(args.soffice).is_file():
        parser.error("LibreOffice not found. Pass --soffice with its executable path.")
    subprocess.run([os.sys.executable, str(ROOT / "tools/build.py")], check=True)
    with TemporaryDirectory(prefix="lod-native-") as directory:
        temporary = Path(directory)
        profile, data = temporary / "profile", temporary / "data"
        command = [args.soffice, "-env:UserInstallation=" + profile.as_uri(), "--headless", "--nologo", "--norestore"]
        env = dict(os.environ, LOD_PANE_DATA_DIR=str(data))
        # First startup creates the default Basic library. Add the probe afterwards.
        subprocess.run(command + ["--terminate_after_init"], env=env, check=True, timeout=30, capture_output=True)
        basic = profile / "user/basic"
        (basic / "Standard").mkdir(parents=True, exist_ok=True)
        (basic / "script.xlc").write_text('''<?xml version="1.0"?><library:libraries xmlns:library="http://openoffice.org/2000/library" xmlns:xlink="http://www.w3.org/1999/xlink"><library:library library:name="Standard" library:link="false"/></library:libraries>''')
        (basic / "Standard/script.xlb").write_text('''<?xml version="1.0"?><library:library xmlns:library="http://openoffice.org/2000/library" library:name="Standard" library:readonly="false" library:passwordprotected="false"><library:element library:name="LODTest"/></library:library>''')
        extension = temporary / "extension"
        with ZipFile(ROOT / "dist/lod-pane.oxt") as archive:
            assert '<version value="0.7.0"/>' in archive.read("description.xml").decode()
            assert 'VERSION = "v0.7.0"' in archive.read("panel.py").decode()
            archive.extractall(extension)
        # Replace only external dictionary I/O in the temporary extracted package.
        # All controls, listeners, factory, core parser and SQLite code are real.
        panel_path = extension / "panel.py"
        fixture = json.loads((ROOT / "tests/fixtures/wieder.json").read_text())
        # More meanings than the old five-meaning and ten-word UI limits.
        meanings = fixture["entry"]["microStructures"][0]["grammaticalUnits"][0]["meanings"]
        meanings[2]["examples"] = []
        for index in range(4, 13):
            meaning = deepcopy(meanings[0])
            meaning["meaningID"] = "WIEDER1UNI%d" % index
            meaning["targetLanguages"]["en"]["parts"][0]["content"] = "Test meaning %d" % index
            meanings.append(meaning)
        meanings[-1]["targetLanguages"]["en"]["parts"][0]["content"] += " long translation" * 35
        meanings[-1]["declensionInfo"] = "Long grammar information " * 35
        moien = json.loads((ROOT / "tests/fixtures/moien.json").read_text())
        panel_path.write_text(panel_path.read_text() + '\n_fixture = ' + repr(fixture) + '\n_moien = ' + repr(moien) + '''
def _fixture_fetch(path):
    if path.startswith("/search?"):
        return {"results": [{"id": "MOIEN1", "word_lb": "Moien"}, {"id": "MOIEN2", "word_lb": "moien"}]} if "Moien" in path else {"results": [{"id": "WIEDER1", "word_lb": "Wieder"}]}
    return _moien if path == "/entry/MOIEN1" else _fixture
lodpane.fetch_json = _fixture_fetch
''')
        report = temporary / "result.txt"
        macro = f'''Sub Main
On Error GoTo Failed
Dim ctx As Object, loader As Object, factory As Object, instance As Object, doc As Object, frame As Object, element As Object, panel As Object, root As Object
Dim stage As String
stage = "factory and all native controls"
ctx = GetDefaultContext()
loader = ctx.ServiceManager.createInstanceWithContext("com.sun.star.loader.Python", ctx)
factory = loader.activate("org.lodpane.PanelFactory", "", "{panel_path.as_uri()}", Nothing)
instance = factory.createInstanceWithContext(ctx)
doc = StarDesktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, Array())
frame = doc.CurrentController.Frame
Dim props(2) As New com.sun.star.beans.PropertyValue
props(0).Name = "Frame"
props(0).Value = frame
props(1).Name = "ParentWindow"
Dim testHost As Object, hostModel As Object, hostToolkit As Object
testHost = CreateUnoService("com.sun.star.awt.UnoControlDialog")
hostModel = CreateUnoService("com.sun.star.awt.UnoControlDialogModel")
hostModel.Title = "LOD pane isolated input probe"
testHost.setModel(hostModel)
hostToolkit = CreateUnoService("com.sun.star.awt.Toolkit")
testHost.createPeer(hostToolkit, Nothing)
testHost.setPosSize(0, 0, 420, 1800, 15)
testHost.setVisible(True)
props(1).Value = testHost.getPeer()
props(2).Name = "Theme"
Dim themeSource As Object
themeSource = CreateUnoService("com.sun.star.awt.UnoControlFixedTextModel")
themeSource.BackgroundColor = 16777215
themeSource.TextColor = 1585727
props(2).Value = themeSource
element = instance.createUIElement("private:resource/toolpanel/LODPane/Notebook", props())
panel = element.getRealInterface()
root = panel.Window
root.setPosSize(0, 0, 336, 1800, 15)
If root.getControl("word").getModel().Label <> "Select a word." Then Call CheckFailed(stage, 1001)
If root.getControl("status").isVisible() Then Call CheckFailed(stage, 1033)
If root.getControl("version").isVisible() Then Call CheckFailed(stage, 1047)
stage = "automatic document selection and queued lookup"
doc.Text.String = "Haut ass d'Wieder schéin."
Dim cursor As Object
cursor = doc.Text.createTextCursor()
cursor.gotoStart(False)
cursor.goRight(11, False)
cursor.goRight(6, True)
doc.CurrentController.select(cursor)
Dim i As Integer
For i = 1 To 60
 Wait 100
 DoEvents
 If root.getControl("word").getModel().Label = "Wieder" Then Exit For
Next i
If root.getControl("word").getModel().Label <> "Wieder" Then Call CheckFailed(stage, 1002)
If root.getControl("meaning").getModel().Label <> "weather" Then Call CheckFailed(stage, 1003)
stage = "same word at another location refreshes its paragraph"
Dim repeatedText As String, secondWordAt As Integer, contextAction As New com.sun.star.awt.ActionEvent
repeatedText = "First scene has Wieder. Second scene has Wieder."
secondWordAt = InStr(InStr(repeatedText, "Wieder") + 6, repeatedText, "Wieder")
doc.Text.String = repeatedText
cursor = doc.Text.createTextCursor()
cursor.gotoStart(False)
cursor.goRight(secondWordAt - 1, False)
cursor.goRight(6, True)
doc.CurrentController.select(cursor)
For i = 1 To 20
 Wait 50
 DoEvents
Next i
contextAction.Source = root.getControl("context")
panel.actionPerformed(contextAction)
If root.getControl("context_text").getModel().Label <> repeatedText Then Call CheckFailed(stage, 1125)
panel.actionPerformed(contextAction)
doc.Text.String = "Haut ass d'Wieder schéin."
cursor = doc.Text.createTextCursor()
cursor.gotoStart(False)
cursor.goRight(11, False)
cursor.goRight(6, True)
doc.CurrentController.select(cursor)
For i = 1 To 20
 Wait 50
 DoEvents
Next i
stage = "host theme adoption and native metrics"
If root.getModel().BackgroundColor <> 16777215 Then Call CheckFailed(stage, 1019)
If Not root.getControl("search").getModel().supportsService("com.sun.star.awt.UnoControlButtonModel") Then Call CheckFailed(stage, 1043)
If Not root.getControl("search").getModel().Tabstop Then Call CheckFailed(stage, 1044)
If Not root.getControl("lang_en").getModel().Toggle Then Call CheckFailed(stage, 1045)
If Not root.getControl("save").getModel().supportsService("com.sun.star.awt.UnoControlButtonModel") Then Call CheckFailed(stage, 1050)
If Not root.getControl("save").getModel().Tabstop Then Call CheckFailed(stage, 1051)
Dim wordFont As Single
wordFont = root.getControl("word").getModel().FontHeight
If wordFont < 14 Or wordFont > 18 Then Call CheckFailed(stage, 1020)
Dim searchRect As New com.sun.star.awt.Rectangle
Dim queryRect As New com.sun.star.awt.Rectangle
searchRect = root.getControl("search").getPosSize()
queryRect = root.getControl("query").getPosSize()
If searchRect.Height <> queryRect.Height Then Call CheckFailed(stage, 1021)
If root.getControl("save").getPosSize().Height > 32 Then Call CheckFailed(stage, 1022)
Dim langRect As New com.sun.star.awt.Rectangle
langRect = root.getControl("lang_en").getPosSize()
If langRect.Width < 60 Then Call CheckFailed(stage, 1034)
If root.getControl("dest_study").getPosSize().Width < 60 Then Call CheckFailed(stage, 1035)
Dim flatSupport As String
flatSupport = ""
If root.getControl("search").getModel().getPropertySetInfo().hasPropertyByName("VisualEffect") Then flatSupport = flatSupport & "VisualEffect "
If root.getControl("search").getModel().getPropertySetInfo().hasPropertyByName("Border") Then flatSupport = flatSupport & "Border "
If root.getControl("query").getModel().getPropertySetInfo().hasPropertyByName("Border") Then flatSupport = flatSupport & "EditBorder "
stage = "note, theme, context, and save event dispatch"
If Not root.getControl("meanings").isVisible() Then Call CheckFailed(stage, 1017)
If InStr(root.getControl("meanings").getModel().Label, "1 of 12") = 0 Then Call CheckFailed(stage, 1018)
If root.getControl("sense0").isVisible() Then Call CheckFailed(stage, 1042)
Call ClickOnce(root, "meanings")
If Not root.getControl("sense0").isVisible() Then Call CheckFailed(stage, 1074)
If InStr(root.getControl("sense0").getModel().Label, "weather") = 0 Then Call CheckFailed(stage, 1074)
Call ClickOnce(root, "meanings")
If root.getControl("note").isVisible() Then Call CheckFailed(stage, 1052)
Dim action As New com.sun.star.awt.ActionEvent
Dim keyEvent As New com.sun.star.awt.KeyEvent
Dim toolkit As Object
toolkit = CreateUnoService("com.sun.star.awt.Toolkit")
root.getControl("note_toggle").setFocus()
keyEvent.Source = root.getControl("note_toggle").getPeer()
keyEvent.KeyCode = com.sun.star.awt.Key.RETURN
toolkit.keyPress(keyEvent)
toolkit.keyRelease(keyEvent)
Wait 100
DoEvents
If Not root.getControl("note").isVisible() Then Call CheckFailed(stage, 1053)
If UBound(root.getTabControllers()) <> 0 Then Call CheckFailed(stage, 1068)
root.getControl("note").setText("Native notebook note.")
root.getControl("settings").setFocus()
keyEvent.Source = root.getControl("settings").getPeer()
keyEvent.KeyCode = com.sun.star.awt.Key.SPACE
toolkit.keyPress(keyEvent)
toolkit.keyRelease(keyEvent)
Wait 100
DoEvents
If Not root.getControl("version").isVisible() Then Call CheckFailed(stage, 1054)
If root.getControl("version").getModel().Label <> "v0.7.0" Then Call CheckFailed(stage, 1055)
action.Source = root.getControl("theme")
panel.actionPerformed(action)
If root.getControl("theme").getModel().Label <> "Use light theme" Then Call CheckFailed(stage, 1004)
If root.getModel().BackgroundColor <> 1121582 Then Call CheckFailed(stage, 1046)
If root.getControl("note").getText() <> "Native notebook note." Then Call CheckFailed(stage, 1005)
action.Source = root.getControl("context")
panel.actionPerformed(action)
Call ClickOnce(root, "save")
If root.getControl("save").getModel().Label <> "Saved to Study" Then Call CheckFailed(stage, 1006)
If root.getControl("save").getModel().Enabled Then Call CheckFailed(stage, 1056)
stage = "second sense has its own draft"
Call ClickOnce(root, "meanings")
Call ClickOnce(root, "sense1")
stage = "second sense click: " & root.getControl("meanings").getModel().Label & " / " & root.getControl("meaning").getModel().Label & " / " & root.getControl("status").getModel().Label & " / y=" & root.getControl("sense1").getPosSize().Y
If root.getControl("note").getText() <> "" Then Call CheckFailed(stage, 1007)
If root.getControl("note").isVisible() Then Call CheckFailed(stage, 1057)
action.Source = root.getControl("note_toggle")
panel.actionPerformed(action)
root.getControl("note").setText("Second meaning note.")
Call ClickOnce(root, "lang_fr")
If root.getControl("note").getText() <> "Second meaning note." Then Call CheckFailed(stage, 1058)
Call ClickOnce(root, "lang_en")
Call ClickOnce(root, "dest_favorites")
If root.getControl("save").getModel().Label <> "Save to Favorites" Then Call CheckFailed(stage, 1075)
Call ClickOnce(root, "dest_study")
Call ClickOnce(root, "meanings")
Call ClickOnce(root, "sense2")
If root.getControl("example").isVisible() Or root.getControl("example_label").isVisible() Then Call CheckFailed(stage, 1091)
Call ClickOnce(root, "meanings")
Call ClickOnce(root, "sense1")
If root.getControl("note").getText() <> "Second meaning note." Then Call CheckFailed(stage, 1092)
action.Source = root.getControl("save")
panel.actionPerformed(action)
If root.getControl("library").getModel().Label <> "Saved 2" Then Call CheckFailed(stage, 1008)
stage = "saved vocabulary and back action"
action.Source = root.getControl("library")
panel.actionPerformed(action)
If InStr(root.getControl("row0").getModel().Label, "Wieder") = 0 Then Call CheckFailed(stage, 1009)
If root.getControl("row1").isVisible() = False Then Call CheckFailed(stage, 1040)
If root.getControl("row2").isVisible() = True Then Call CheckFailed(stage, 1041)
panel.actionPerformed(action)
If root.getControl("note").getText() <> "Second meaning note." Then Call CheckFailed(stage, 1010)
stage = "native size contract and cleanup"
Dim size As New com.sun.star.ui.LayoutSize
size = panel.getHeightForWidth(288)
If size.Minimum <> size.Preferred Or size.Maximum <> -1 Or size.Minimum < 360 Then Call CheckFailed(stage, 1011)
Dim wideSize As New com.sun.star.ui.LayoutSize
wideSize = panel.getHeightForWidth(1000)
If wideSize.Minimum > size.Minimum Then Call CheckFailed(stage, 1016)
size = panel.getHeightForWidth(288)
If panel.getMinimalWidth() <> 288 Then Call CheckFailed(stage, 1012)
Dim saveRect As New com.sun.star.awt.Rectangle
saveRect = root.getControl("save").getPosSize()
If saveRect.X < 16 Or saveRect.X + saveRect.Width > 288 Then Call CheckFailed(stage, 1013)
stage = "wide deck stays inside a centered column: resize"
testHost.setPosSize(0, 0, 1100, 1800, 15)
panel.Window.setPosSize(0, 0, 1000, 1800, 15)
Dim wideEvent As New com.sun.star.awt.WindowEvent
wideEvent.Width = 1000
wideEvent.Height = 1800
panel.windowResized(wideEvent)
stage = "save row sits below the entry content"
If root.getControl("save").getPosSize().Y <= root.getControl("note").getPosSize().Y Then Call CheckFailed(stage, 1036)
stage = "wide deck stays inside a centered column: measure"
Dim wideRect As New com.sun.star.awt.Rectangle
wideRect = root.getControl("save").getPosSize()
If wideRect.Width > 420 Then Call CheckFailed(stage, 1032)
If wideRect.X < 16 Or wideRect.X + wideRect.Width > 1000 Then Call CheckFailed(stage, 1014)
If root.getControl("search").getPosSize().X + root.getControl("search").getPosSize().Width > 1000 - 16 Then Call CheckFailed(stage, 1015)
stage = "report state before teardown"
Dim statusText As String, libraryText As String, saveText As String
statusText = root.getControl("status").getModel().Label
libraryText = root.getControl("library").getModel().Label
saveText = root.getControl("save").getModel().Label
stage = "layout lint: no overlaps or dead gaps"
Dim lintReport As String
Dim controls As Variant, widths As Variant
Dim a As Integer, b As Integer, w As Integer
controls = root.getControls()
widths = Array(288, 336, 1000)
Call ClickOnce(root, "meanings")
For w = 0 To UBound(widths)
 size = panel.getHeightForWidth(widths(w))
 For a = 0 To UBound(controls)
  If controls(a).getModel().supportsService("com.sun.star.awt.UnoControlListBoxModel") Or controls(a).getModel().supportsService("com.sun.star.awt.UnoControlFixedHyperlinkModel") Then Call CheckFailed(stage, 1093)
  For b = a + 1 To UBound(controls)
   Dim ra As New com.sun.star.awt.Rectangle
   Dim rb As New com.sun.star.awt.Rectangle
   ra = controls(a).getPosSize()
   rb = controls(b).getPosSize()
   If controls(a).isVisible() And controls(b).isVisible() Then
    If ra.X < rb.X + rb.Width And rb.X < ra.X + ra.Width And ra.Y < rb.Y + rb.Height And rb.Y < ra.Y + ra.Height Then
     lintReport = lintReport & "overlap " & a & "/" & b & " at width " & widths(w) & " ; "
    End If
   End If
  Next b
 Next a
Next w
Call ClickOnce(root, "meanings")
If Len(lintReport) > 0 Then
 Open "{report}" For Output As #2
 Print #2, "FAIL layout lint: " & lintReport
 Close #2
 StarDesktop.terminate()
 Exit Sub
End If
stage = "all meanings and saved-word pages remain reachable"
For i = 2 To 11
 Call ClickOnce(root, "meanings")
 If i Mod 5 = 0 Then Call ClickOnce(root, "sense_next")
 Call ClickOnce(root, "sense" & (i Mod 5))
 root.getControl("note").setText("Meaning " & (i + 1))
 action.Source = root.getControl("save")
 panel.actionPerformed(action)
Next i
stage = "saved pages: " & root.getControl("library").getModel().Label & " / " & root.getControl("meanings").getModel().Label & " / " & root.getControl("status").getModel().Label
action.Source = root.getControl("library")
panel.actionPerformed(action)
If Not root.getControl("next").isVisible() Then Call CheckFailed(stage, 1059)
If root.getControl("previous").getModel().Enabled Then Call CheckFailed(stage, 1060)
action.Source = root.getControl("next")
panel.actionPerformed(action)
If root.getControl("next").getModel().Enabled Then Call CheckFailed(stage, 1061)
If Not root.getControl("row1").isVisible() Then Call CheckFailed(stage, 1062)
root.getControl("filter").setText("Meaning 12")
If root.getControl("next").isVisible() Then Call CheckFailed(stage, 1063)
If root.getControl("row1").isVisible() Then Call CheckFailed(stage, 1064)
If InStr(root.getControl("row0").getModel().Label, "Test meaning 12") = 0 Then Call CheckFailed(stage, 1065)
action.Source = root.getControl("row0")
panel.actionPerformed(action)
If root.getControl("note").getText() <> "Meaning 12" Then Call CheckFailed(stage, 1066)
stage = "long dictionary text wraps without fixed-height clipping"
size = panel.getHeightForWidth(288)
If root.getControl("meaning").getPosSize().Height <= 28 Then Call CheckFailed(stage, 1071)
If root.getControl("grammar").getPosSize().Height <= 28 Then Call CheckFailed(stage, 1072)
wideSize = panel.getHeightForWidth(1000)
If wideSize.Preferred >= size.Preferred Then Call CheckFailed(stage, 1073)
stage = "Moien regression: one click synchronizes meaning, grammar and example"
root.getControl("query").setText("Moien")
root.getControl("query").setFocus()
keyEvent.Source = root.getControl("query").getPeer()
keyEvent.KeyCode = com.sun.star.awt.Key.RETURN
toolkit.keyPress(keyEvent)
toolkit.keyRelease(keyEvent)
For i = 1 To 60
 Wait 100
 DoEvents
 If root.getControl("word").getModel().Label = "Which word?" Then Exit For
Next i
If root.getControl("word").getModel().Label <> "Which word?" Then Call CheckFailed(stage, 1076)
Call ClickOnce(root, "row0")
For i = 1 To 60
 Wait 100
 DoEvents
 If root.getControl("word").getModel().Label = "Moien" Then Exit For
Next i
If root.getControl("meaning").getModel().Label <> "morning (first part of the day)" Then Call CheckFailed(stage, 1077)
If root.getControl("example").getModel().Label <> "mäi Papp mécht all Moien de Baart" Then Call CheckFailed(stage, 1078)
Call ClickOnce(root, "meanings")
Call ClickOnce(root, "sense2")
If root.getControl("meaning").getModel().Label <> "to say hello" Then Call CheckFailed(stage, 1079)
If root.getControl("grammar").isVisible() Then Call CheckFailed(stage, 1080)
Dim moienExample As String
moienExample = "déi onfrëndlech Vendeuse huet net emol Moie gesot, wéi mer an de Buttek erakomm sinn"
If root.getControl("example").getModel().Label <> moienExample Then Call CheckFailed(stage, 1081)
If root.getControl("example_label").getModel().Label <> "Example · Luxembourgish" Then Call CheckFailed(stage, 1082)
Call ClickOnce(root, "lang_fr")
If root.getControl("lang_fr").getModel().State <> 1 Or root.getControl("lang_en").getModel().State <> 0 Then Call CheckFailed(stage, 1094)
If root.getControl("meaning").getModel().Label <> "dire bonjour (à) · saluer" Then Call CheckFailed(stage, 1083)
If root.getControl("example").getModel().Label <> moienExample Then Call CheckFailed(stage, 1084)
If Left(root.getControl("lang_fr").getModel().Label, 1) <> "✓" Then Call CheckFailed(stage, 1085)
If root.getControl("lang_fr").getModel().BackgroundColor = root.getControl("lang_en").getModel().BackgroundColor Then Call CheckFailed(stage, 1086)
Call ClickOnce(root, "lang_de")
If root.getControl("meaning").getModel().Label <> "grüßen · Hallo sagen" Then Call CheckFailed(stage, 1087)
Call ClickOnce(root, "lang_en")
Call ClickOnce(root, "meanings")
Call ClickOnce(root, "sense0")
If root.getControl("meaning").getModel().Label <> "morning (first part of the day)" Then Call CheckFailed(stage, 1088)
If Not root.getControl("grammar").isVisible() Then Call CheckFailed(stage, 1089)
If root.getControl("example").getModel().Label <> "mäi Papp mécht all Moien de Baart" Then Call CheckFailed(stage, 1090)
stage = "replacement preview, exact edit and native Undo"
Dim beforeDocument As String
beforeDocument = doc.Text.String
cursor.CharWeight = 150
doc.getUndoManager().clear()
Call ClickOnce(root, "note_toggle")
root.getControl("note").setText("Keep the Moien draft.")
Call ClickOnce(root, "replace_toggle")
If doc.Text.String <> beforeDocument Then Call CheckFailed(stage, 1100)
If InStr(root.getControl("replace_preview").getModel().Label, "Wieder") = 0 Then Call CheckFailed(stage, 1101)
If InStr(root.getControl("replace_preview").getModel().Label, "Moien") = 0 Then Call CheckFailed(stage, 1102)
Call ClickOnce(root, "replace_confirm")
If doc.Text.String <> Replace(beforeDocument, "Wieder", "Moien") Then Call CheckFailed(stage, 1103)
If Not doc.getUndoManager().isUndoPossible() Then Call CheckFailed(stage, 1104)
If doc.getUndoManager().getCurrentUndoActionTitle() <> "Replace with LOD headword" Then Call CheckFailed(stage, 1105)
Dim edited As Object
edited = doc.Text.createTextCursor()
edited.gotoStart(False)
edited.goRight(11, False)
edited.goRight(5, True)
If edited.CharWeight <> 150 Then Call CheckFailed(stage, 1106)
doc.getUndoManager().undo()
If doc.Text.String <> beforeDocument Then Call CheckFailed(stage, 1107)
Call ClickOnce(root, "home")
Wait 800
DoEvents
If root.getControl("word").getModel().Label <> "Select a word." Then Call CheckFailed(stage, 1108)
If root.getControl("query").getText() <> "" Then Call CheckFailed(stage, 1109)
If root.getControl("replace_confirm").isVisible() Then Call CheckFailed(stage, 1110)
Call OpenMoien(root)
If root.getControl("note").getText() <> "Keep the Moien draft." Then Call CheckFailed(stage, 1111)
stage = "identical text at another location cannot reuse a replacement preview"
doc.Text.String = "Wieder Wieder"
Dim firstWord As Object, secondWord As Object
firstWord = doc.Text.createTextCursor()
firstWord.gotoStart(False)
firstWord.goRight(6, True)
doc.CurrentController.select(firstWord)
Call OpenMoien(root)
Call ClickOnce(root, "replace_toggle")
secondWord = doc.Text.createTextCursor()
secondWord.gotoStart(False)
secondWord.goRight(7, False)
secondWord.goRight(6, True)
doc.CurrentController.select(secondWord)
Call ClickOnce(root, "replace_confirm")
If doc.Text.String <> "Wieder Wieder" Then Call CheckFailed(stage, 1112)
If InStr(root.getControl("status").getModel().Label, "selection changed") = 0 Then Call CheckFailed(stage, 1113)
If root.getControl("replace_confirm").getModel().Enabled Then Call CheckFailed(stage, 1114)
stage = "Home from Saved and queued lookup cancellation"
Call ClickOnce(root, "library")
Call ClickOnce(root, "home")
If root.getControl("word").getModel().Label <> "Select a word." Then Call CheckFailed(stage, 1115)
If root.getControl("library").getModel().Label <> "Saved 12" Then Call CheckFailed(stage, 1116)
root.getControl("query").setText("Moien")
action.Source = root.getControl("search")
panel.actionPerformed(action)
Call ClickOnce(root, "home")
Wait 800
DoEvents
If root.getControl("word").getModel().Label <> "Select a word." Then Call CheckFailed(stage, 1117)
If doc.Text.String <> "Wieder Wieder" Then Call CheckFailed(stage, 1118)
stage = "read-only document rejects replacement before editing"
Dim storeArgs(0) As New com.sun.star.beans.PropertyValue
storeArgs(0).Name = "FilterName"
storeArgs(0).Value = "writer8"
doc.storeToURL("{(temporary / 'readonly.odt').as_uri()}", storeArgs())
Dim roArgs(1) As New com.sun.star.beans.PropertyValue
roArgs(0).Name = "ReadOnly"
roArgs(0).Value = True
roArgs(1).Name = "Hidden"
roArgs(1).Value = True
Dim roDoc As Object, roElement As Object, roPanel As Object, roRoot As Object, roCursor As Object
roDoc = StarDesktop.loadComponentFromURL("{(temporary / 'readonly.odt').as_uri()}", "_blank", 0, roArgs())
If Not roDoc.isReadonly() Then Call CheckFailed(stage, 1121)
root.setVisible(False)
props(0).Value = roDoc.CurrentController.Frame
roElement = instance.createUIElement("private:resource/toolpanel/LODPane/Notebook", props())
roPanel = roElement.getRealInterface()
roRoot = roPanel.Window
roRoot.setPosSize(0, 0, 336, 1800, 15)
roCursor = roDoc.Text.createTextCursor()
roCursor.gotoStart(False)
roCursor.goRight(6, True)
roDoc.CurrentController.select(roCursor)
For i = 1 To 60
 Wait 100
 DoEvents
 If roRoot.getControl("word").getModel().Label = "Wieder" Then Exit For
Next i
If roRoot.getControl("word").getModel().Label <> "Wieder" Then Call CheckFailed(stage, 1122)
Call ClickOnce(roRoot, "replace_toggle")
If InStr(roRoot.getControl("status").getModel().Label, "read-only") = 0 Then Call CheckFailed(stage, 1123)
If roDoc.Text.String <> "Wieder Wieder" Then Call CheckFailed(stage, 1124)
roElement.dispose()
roDoc.close(True)
root.setVisible(True)
stage = "cleanup: element released cleanly"
Dim teardown As String
On Error Resume Next
teardown = element.getResourceURL()
If Err <> 0 Then
 Err = 0
 teardown = "host released the element during resize; panel teardown was already handled"
Else
 element.dispose()
 If Err <> 0 Then
  teardown = "dispose failed after host teardown: " & Err & " " & Error$
  Err = 0
 Else
  teardown = "disposed by the test without error"
 End If
End If
On Error GoTo Failed
If InStr(teardown, "failed") > 0 Then Call CheckFailed(stage, 1031)
Open "{report}" For Output As #1
Print #1, "PASS"
Dim prefSize As New com.sun.star.ui.LayoutSize
prefSize = panel.getHeightForWidth(288)
Print #1, "empty state height " & prefSize.Preferred
Print #1, "word font " & wordFont
Print #1, "save rect " & root.getControl("save").getPosSize().X & "," & root.getControl("save").getPosSize().Width & " h" & root.getControl("save").getPosSize().Height
Print #1, "search rect " & searchRect.X & "," & searchRect.Width & " h" & searchRect.Height
Print #1, "flat styling available: " & flatSupport
Print #1, "layout lint clean"
Print #1, "teardown " & teardown
Print #1, "status label " & statusText
Print #1, "library label " & libraryText
Print #1, "save label " & saveText
Close #1
testHost.dispose()
StarDesktop.terminate()
Exit Sub
Failed:
Open "{report}" For Output As #2
Print #2, "FAIL at " & stage & ": " & Err & " " & Error$
Close #2
StarDesktop.terminate()
End Sub

' Do not rely on user-defined Error numbers: failures must never reach PASS.
Sub CheckFailed(stage As String, code As Integer)
Open "{report}" For Output As #3
Print #3, "FAIL at " & stage & ": assertion " & code
Close #3
StarDesktop.terminate()
End
End Sub

Sub OpenMoien(root As Object)
Dim toolkit As Object
Dim key As New com.sun.star.awt.KeyEvent
toolkit = CreateUnoService("com.sun.star.awt.Toolkit")
root.getControl("query").setText("Moien")
root.getControl("query").setFocus()
key.Source = root.getControl("query").getPeer()
key.KeyCode = com.sun.star.awt.Key.RETURN
toolkit.keyPress(key)
toolkit.keyRelease(key)
Dim n As Integer
For n = 1 To 60
 Wait 100
 DoEvents
 If root.getControl("word").getModel().Label = "Which word?" Then Exit For
Next n
If root.getControl("word").getModel().Label <> "Which word?" Then Call CheckFailed("open Moien candidates", 1119)
Call ClickOnce(root, "row0")
For n = 1 To 60
 Wait 100
 DoEvents
 If root.getControl("word").getModel().Label = "Moien" Then Exit For
Next n
If root.getControl("word").getModel().Label <> "Moien" Then Call CheckFailed("open Moien entry", 1120)
End Sub

Sub ClickOnce(root As Object, name As String)
Dim mouse As New com.sun.star.awt.MouseEvent
Dim toolkit As Object
toolkit = CreateUnoService("com.sun.star.awt.Toolkit")
mouse.Source = root.getControl(name).getPeer()
mouse.Buttons = 1
mouse.ClickCount = 1
mouse.X = root.getControl(name).getPosSize().Width - 3
mouse.Y = root.getControl(name).getPosSize().Height \\ 2
toolkit.mousePress(mouse)
toolkit.mouseRelease(mouse)
' Keep independent single clicks outside the platform double-click interval.
Wait 550
DoEvents
End Sub'''
        (basic / "Standard/LODTest.xba").write_text('<?xml version="1.0" encoding="UTF-8"?><script:module xmlns:script="http://openoffice.org/2000/script" script:name="LODTest" script:language="StarBasic">' + escape(macro) + '</script:module>')
        try:
            result = subprocess.run(command + ["--nodefault", "macro:///Standard.LODTest.Main()"], env=env, timeout=120, capture_output=True, text=True)
            stderr = result.stderr
        except subprocess.TimeoutExpired as timeout:
            subprocess.run(["pkill", "-f", str(temporary)], capture_output=True)
            stderr = (timeout.stderr or b"").decode(errors="replace") if isinstance(timeout.stderr, bytes) else (timeout.stderr or "")
            raise AssertionError("LibreOffice probe did not finish; macro likely stopped early.\n" + (report.read_text() if report.exists() else "no report") + "\n" + ((data / "panel-error.log").read_text() if (data / "panel-error.log").exists() else "") + stderr) from None
        message = report.read_text().strip() if report.exists() else "Native probe did not run. " + stderr
        error_log = data / "panel-error.log"
        assert message.startswith("PASS"), message + ("\n" + error_log.read_text() if error_log.exists() else "")
        with sqlite3.connect(data / "vocabulary.sqlite3") as db:
            saved = [json.loads(row[0]) for row in db.execute("SELECT value FROM words")]
            prefs = dict(db.execute("SELECT key, value FROM settings"))
        assert len(saved) == 12, (message, [(item["key"], item["note"], item["context"], item["destination"]) for item in saved])
        first = next(item for item in saved if item["senseId"] == "WIEDER1UNI1")
        assert first["note"] == "Native notebook note."
        assert first["context"] == "Haut ass d'Wieder schéin."
        assert prefs["theme"] == "dark"
        print("PASS: native buttons, same-word context refresh, optimistic saves, Moien meanings/languages/examples, previewed range replacement, formatting/native Undo, stale-location rejection, Home/draft preservation/cancellation, and vocabulary/layout. Isolated dialog/profile only, not a real-sidebar acceptance test.")
        print("      " + message.replace(chr(10), chr(10) + "      "))


if __name__ == "__main__":
    main()
