import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

ListView {
    id: root

    property var operations: []
    model: operations
    spacing: Style.spacing.md
    clip: true

    delegate: Ui.BorderSurface {
        id: operationRow
        required property var modelData
        width: ListView.view.width
        implicitHeight: row.implicitHeight + Style.spacing.rowPaddingX * 2
        color: Style.normalFill
        radius: Style.cornerRadius
        borderSpec: Border.controlSpec("normal", Color.foreground, Color.accent)

        ColumnLayout {
            id: row
            anchors.fill: parent
            anchors.margins: Style.spacing.rowPaddingX
            spacing: Style.spacing.md

            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: operationRow.modelData.summary || operationRow.modelData.kind || "Change"
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                    wrapMode: Text.WordWrap
                }
                Text {
                    visible: operationRow.modelData.inverse === null
                    text: "Not reversible"
                    color: Color.urgent
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption
                }
            }

            Repeater {
                model: operationRow.modelData.warnings || []
                delegate: Text {
                    required property var modelData
                    Layout.fillWidth: true
                    text: modelData.message || String(modelData)
                    color: Color.urgent
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                }
            }

            DiffView {
                Layout.fillWidth: true
                Layout.preferredHeight: visible ? Style.space(180) : 0
                visible: operationRow.modelData.detail && operationRow.modelData.detail.diff
                diff: visible ? operationRow.modelData.detail.diff : ""
            }
        }
    }
}
