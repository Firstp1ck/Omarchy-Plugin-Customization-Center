import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

ColumnLayout {
    id: root
    property var row: null
    signal editRequested(var row)
    signal removeRequested(var row)
    signal disableRequested(var row)
    signal replaceRequested(var row)
    spacing: Style.spacing.md

    Text { text: root.row ? String(root.row.display || root.row.keyToken) : "Select a binding"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; font.bold: true }
    Text { Layout.fillWidth: true; text: root.row ? String(root.row.description || "No description") : "Choose a row to inspect its source, flags, and recovery action."; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.body; wrapMode: Text.WordWrap }
    Text { Layout.fillWidth: true; visible: root.row !== null; text: root.row ? "Source: " + String(root.row.classification) + "\nSetting: global " + String(root.row.phase) + " binding\nFile: ~/.config/hypr/bindings.lua" : ""; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall; wrapMode: Text.WordWrap }
    Text { Layout.fillWidth: true; visible: root.row && root.row.readOnlyReason; text: root.row ? "Read-only: " + String(root.row.readOnlyReason) + ". Recovery: edit the exact source binding outside the managed block." : ""; color: Color.urgent; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall; wrapMode: Text.WordWrap }
    RowLayout {
        visible: root.row !== null
        Ui.Button { text: "Edit"; focusable: true; enabled: root.row && root.row.editable && root.row.editable.edit; onClicked: root.editRequested(root.row) }
        Ui.Button { text: "Remove"; focusable: true; enabled: root.row && root.row.classification === "managed"; onClicked: root.removeRequested(root.row) }
        Ui.Button { text: "Disable default"; focusable: true; enabled: root.row && root.row.editable && root.row.editable.disable; onClicked: root.disableRequested(root.row) }
        Ui.Button { text: "Replace default"; focusable: true; enabled: root.row && root.row.editable && root.row.editable.replace; onClicked: root.replaceRequested(root.row) }
    }
}
