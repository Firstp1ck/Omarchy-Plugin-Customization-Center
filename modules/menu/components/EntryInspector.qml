import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

ColumnLayout {
    id: root
    property var row: null
    property var draftEntry: null
    signal fieldEdited(string field, var value)
    signal idEdited(string value)
    signal removeShadowRequested()
    spacing: Style.spacing.md

    EntryForm {
        id: form
        Layout.fillWidth: true
        Layout.fillHeight: true
        entry: root.draftEntry || (root.row ? ({ id: root.row.id, origin: root.row.origin, fields: root.row.fields, passthrough: ({}) }) : null)
        onFieldEdited: (field, value) => root.fieldEdited(field, value)
        onIdEdited: value => root.idEdited(value)
    }
    Ui.Button {
        visible: root.row && root.row.origin === "shadowed"
        text: "Remove shadow"
        bordered: true
        focusable: true
        onClicked: root.removeShadowRequested()
    }
    function focusFirst() { form.focusFirst() }
}
