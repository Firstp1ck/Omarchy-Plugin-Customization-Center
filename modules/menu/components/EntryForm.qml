import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui
import "../../../core" as Core

Flickable {
    id: root
    property var entry: null
    property bool editable: entry && entry.origin === "custom"
    signal fieldEdited(string field, var value)
    signal idEdited(string value)
    contentWidth: width
    contentHeight: form.implicitHeight
    clip: true

    function focusFirst() { idField.forceActiveFocus() }

    ColumnLayout {
        id: form
        width: root.width
        spacing: Style.spacing.lg
        Text { text: root.entry ? (root.editable ? "Edit custom entry" : "Entry details") : "Select a menu entry"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading; font.bold: true }
        Text {
            Layout.fillWidth: true
            visible: root.entry && root.entry.origin === "shadowed"
            text: "This shipped id is shadowed as a whole. Remove the shadow to reveal the shipped setting; field-level override is unavailable."
            color: Color.urgent; font.family: Style.font.family; font.pixelSize: Style.font.body; wrapMode: Text.WordWrap
        }
        Core.FormField {
            Layout.fillWidth: true
            label: "Menu id"
            description: "Lowercase dotted id. Renaming also changes the static route."
            Ui.TextField { id: idField; width: parent.width; text: root.entry ? root.entry.id : ""; readOnly: !root.editable; onEditingFinished: if (root.editable) root.idEdited(text) }
        }
        Core.FormField {
            Layout.fillWidth: true; label: "Label"; description: "The text shown for this setting in the menu."
            Ui.TextField { width: parent.width; text: root.entry && root.entry.fields ? root.entry.fields.label || "" : ""; readOnly: !root.editable; onEditingFinished: if (root.editable) root.fieldEdited("label", text) }
        }
        Core.FormField {
            Layout.fillWidth: true; label: "Icon"; description: "One glyph. The active Omarchy font is used unless iconFont is set."
            Ui.TextField { width: parent.width; text: root.entry && root.entry.fields ? root.entry.fields.icon || "" : ""; readOnly: !root.editable; onEditingFinished: if (root.editable) root.fieldEdited("icon", text) }
        }
        Core.FormField {
            Layout.fillWidth: true; label: "Description"
            Ui.TextField { width: parent.width; text: root.entry && root.entry.fields ? root.entry.fields.description || "" : ""; readOnly: !root.editable; onEditingFinished: if (root.editable) root.fieldEdited("description", text) }
        }
        Core.FormField {
            Layout.fillWidth: true; label: "Command"; description: "Runs through bash -lc only after this row is selected."
            Ui.TextField { width: parent.width; text: root.entry && root.entry.fields ? root.entry.fields.action || "" : ""; readOnly: !root.editable; onEditingFinished: if (root.editable) root.fieldEdited("action", text) }
        }
        Text { text: "Conditions"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; font.bold: true }
        GuardField { Layout.fillWidth: true; label: "When"; value: root.entry && root.entry.fields ? root.entry.fields.when || "" : ""; enabled: root.editable; onEdited: value => root.fieldEdited("when", value) }
        GuardField { Layout.fillWidth: true; label: "Checked"; value: root.entry && root.entry.fields ? root.entry.fields.checked || "" : ""; enabled: root.editable; onEdited: value => root.fieldEdited("checked", value) }
        GuardField { Layout.fillWidth: true; label: "Disabled"; value: root.entry && root.entry.fields ? root.entry.fields.disabled || "" : ""; enabled: root.editable; onEdited: value => root.fieldEdited("disabled", value) }
        Text {
            Layout.fillWidth: true
            visible: root.entry && root.entry.passthrough && Object.keys(root.entry.passthrough).length > 0
            text: "Advanced fields are preserved read-only: " + Object.keys(root.entry.passthrough || {}).join(", ")
            color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap
        }
    }
}
