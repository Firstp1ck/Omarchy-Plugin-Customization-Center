import QtQuick
import QtQuick.Layouts
import qs.Commons

ColumnLayout {
    id: root
    property var findings: []
    spacing: Style.spacing.sm
    visible: findings && findings.length > 0
    Repeater {
        model: root.findings || []
        delegate: Text {
            required property var modelData
            Layout.fillWidth: true
            text: String(modelData.severity || "note").toUpperCase() + ": " + String(modelData.reason || modelData.category)
            color: modelData.severity === "blocker" ? Color.urgent : Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }
    }
}
