import QtQuick
import qs.Commons
import qs.Ui as Ui

Ui.BorderSurface {
    id: root
    property var category: ({})
    readonly property var current: category.current || ({})
    readonly property string valueText: current.choice || current.reported || "No selection"
    implicitHeight: valueColumn.implicitHeight + Style.spacing.md * 2
    color: Style.normalFill
    borderSpec: Border.controlSpec("normal", Color.foreground, Color.accent, Color.urgent)

    Column {
        id: valueColumn
        anchors.fill: parent
        anchors.margins: Style.spacing.md
        spacing: Style.spacing.xs
        Text {
            text: root.category.state === "unknown" ? "Not an Omarchy choice" : "Current: " + root.valueText
            color: root.category.state === "broken" ? Color.urgent : Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.subtitle
            font.bold: true
        }
        Text {
            width: parent.width
            text: root.category.state === "unknown" ? "Raw setting: " + String(root.current.reported || "").replace(/[\x00-\x1f]/g, "�").slice(0, 120) + (root.current.unknownDesktopName ? " · Desktop name: " + root.current.unknownDesktopName : "") : "Health: " + (root.category.state || "loading")
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }
    }
}
