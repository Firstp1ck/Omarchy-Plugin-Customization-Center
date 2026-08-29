import QtQuick
import QtQuick.Layouts
import qs.Commons

ColumnLayout {
    id: root
    property string content: ""
    Text { text: "Managed Lua preview"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; font.bold: true }
    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: Style.space(180)
        color: Style.normalFill
        border.color: Style.normalBorderColor
        border.width: Style.normalBorderWidth
        radius: Style.cornerRadius
        Flickable {
            anchors.fill: parent
            anchors.margins: Style.spacing.md
            contentWidth: preview.paintedWidth
            contentHeight: preview.paintedHeight
            clip: true
            Text { id: preview; text: root.content || "No managed block. Applying an empty model removes it from ~/.config/hypr/bindings.lua."; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
        }
    }
}
