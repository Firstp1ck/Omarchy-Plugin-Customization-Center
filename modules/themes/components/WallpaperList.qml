import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

ColumnLayout {
    id: root
    property var wallpapers: []
    property bool busy: false
    signal patchRequested(var patch)
    spacing: Style.spacing.md
    Text { text: "Wallpapers"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.title; font.bold: true }
    Text { Layout.fillWidth: true; text: "Add local raster files to the draft asset list. File: ~/.config/omarchy/themes/<slug>/backgrounds/. Setting: preferred wallpaper. Recovery: remove a missing or invalid source and choose it again."; color: Color.muted; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.body }
    Repeater {
        model: root.wallpapers
        delegate: RowLayout {
            required property var modelData
            required property int index
            Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: modelData.outputName + "  " + modelData.sourcePath; color: Color.foreground; elide: Text.ElideMiddle; font.family: Style.font.family; font.pixelSize: Style.font.body }
            Ui.Button { text: "Remove"; focusable: true; enabled: !root.busy; onClicked: { var items = root.wallpapers.slice(); items.splice(index, 1); root.patchRequested({ wallpapers: items }) } }
        }
    }
    Text { visible: root.wallpapers.length === 0; text: "Empty. preview.png will be generated and activation will keep the current wallpaper."; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
}
