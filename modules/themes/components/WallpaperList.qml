import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

ColumnLayout {
    id: root
    property var wallpapers: []
    property string preferred: ""
    property bool busy: false
    property string newSource: ""
    property string newName: ""
    signal patchRequested(var patch)
    spacing: Style.spacing.md
    Text { text: "Wallpapers"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.title; font.bold: true }
    Text { Layout.fillWidth: true; text: "Only absolute, regular local raster files are accepted. They are copied into the data-only theme after header, dimension, and size checks."; color: Color.muted; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
    RowLayout {
        Layout.fillWidth: true
        Ui.TextField { Layout.fillWidth: true; text: root.newSource; placeholderText: "/home/user/Pictures/wallpaper.webp"; Accessible.name: "Wallpaper source path"; onTextChanged: root.newSource = text }
        Ui.TextField { Layout.preferredWidth: Style.space(170); text: root.newName; placeholderText: "01-wallpaper.webp"; Accessible.name: "Wallpaper output name"; onTextChanged: root.newName = text }
        Ui.Button {
            text: "Add"; focusable: true; enabled: !root.busy && root.newSource.length > 0 && root.newName.length > 0
            onClicked: { var items = root.wallpapers.slice(); items.push({ sourcePath: root.newSource, outputName: root.newName }); root.patchRequested({ wallpapers: items }); root.newSource = ""; root.newName = "" }
        }
    }
    Repeater {
        model: root.wallpapers
        delegate: Ui.BorderSurface {
            required property var modelData
            required property int index
            Layout.fillWidth: true
            implicitHeight: row.implicitHeight + Style.spacing.sm * 2
            color: Style.normalFill
            borderSpec: Border.controlSpec(modelData.outputName === root.preferred ? "selected" : "normal", Color.foreground, Color.accent)
            RowLayout {
                id: row; anchors.fill: parent; anchors.margins: Style.spacing.sm
                Text { Layout.fillWidth: true; text: modelData.outputName + "  " + modelData.sourcePath; color: Color.foreground; elide: Text.ElideMiddle; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
                Ui.Button { text: "Preferred"; focusable: true; selected: modelData.outputName === root.preferred; onClicked: root.patchRequested({ preferredWallpaper: modelData.outputName }) }
                Ui.Button { text: "↑"; focusable: true; enabled: index > 0; Accessible.name: "Move " + modelData.outputName + " up"; onClicked: { var items = root.wallpapers.slice(); var item = items.splice(index, 1)[0]; items.splice(index - 1, 0, item); root.patchRequested({ wallpapers: items }) } }
                Ui.Button { text: "↓"; focusable: true; enabled: index + 1 < root.wallpapers.length; Accessible.name: "Move " + modelData.outputName + " down"; onClicked: { var items = root.wallpapers.slice(); var item = items.splice(index, 1)[0]; items.splice(index + 1, 0, item); root.patchRequested({ wallpapers: items }) } }
                Ui.Button { text: "Remove"; focusable: true; enabled: !root.busy; onClicked: { var items = root.wallpapers.slice(); items.splice(index, 1); root.patchRequested({ wallpapers: items, preferredWallpaper: modelData.outputName === root.preferred ? null : root.preferred }) } }
            }
        }
    }
    Text { visible: root.wallpapers.length === 0; text: "Empty. preview.png will be generated and activation will keep the current wallpaper."; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
}
