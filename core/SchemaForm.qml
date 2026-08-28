import QtQuick
import QtQuick.Layouts
import qs.Commons

ColumnLayout {
    id: root

    property var schema: ({ fields: [] })
    property var values: ({})
    property bool readOnly: false
    readonly property var fields: schema && schema.fields ? schema.fields : []
    readonly property int renderedFieldCount: fieldRepeater.count

    signal valueChanged(string key, var value)
    signal requestDraftPatch(var patch)
    signal requestDeleteKey(string key)

    spacing: Style.spacing.panelGap

    function fieldTypeAt(index) {
        return index >= 0 && index < fields.length ? String(fields[index].type || "") : ""
    }

    function fieldAt(index) {
        return fieldRepeater.itemAt(index)
    }

    function editValue(key, value) {
        if (readOnly) return
        var patch = ({})
        patch[key] = value
        valueChanged(key, value)
        requestDraftPatch(patch)
    }

    Repeater {
        id: fieldRepeater
        model: root.fields
        delegate: SchemaField {
            required property var modelData
            Layout.fillWidth: true
            field: modelData
            values: root.values
            readOnly: root.readOnly
            onValueEdited: function(key, value) {
                if (root.readOnly) return
                root.editValue(key, value)
            }
            onRequestDeleteKey: function(key) {
                if (!root.readOnly) root.requestDeleteKey(key)
            }
        }
    }
}
