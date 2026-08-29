import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

ColumnLayout {
    id: root
    property var row: null
    property var validation: null
    property bool canValidate: false
    signal validateRequested(string pluginId)
    spacing: Style.spacing.md
    Text { text: "Diagnostics"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle }
    Repeater {
        model: root.row ? root.row.diagnostics || [] : []
        Text { required property var modelData; Layout.fillWidth: true; wrapMode: Text.WordWrap; text: modelData.code + ": " + modelData.message; color: modelData.severity === "error" ? Color.urgent : Color.foreground; font.family: Style.font.family }
    }
    Text { Layout.fillWidth: true; visible: !!root.row && (root.row.diagnostics || []).length === 0; text: "No error observed while this page was open. The shell does not expose a persistent health record."; color: Color.muted; font.family: Style.font.family }
    Text { Layout.fillWidth: true; visible: !!root.validation; wrapMode: Text.WrapAnywhere; text: root.validation ? "Validation exit " + root.validation.exit + "\n" + (root.validation.stderr || root.validation.stdout || "No output") : ""; color: root.validation && root.validation.exit !== 0 ? Color.urgent : Color.foreground; font.family: Style.font.family }
    Ui.Button { objectName: "validatePluginButton"; text: "Run validation"; visible: !!root.row && root.canValidate; focusable: true; onClicked: if (root.row) root.validateRequested(root.row.id) }
}
