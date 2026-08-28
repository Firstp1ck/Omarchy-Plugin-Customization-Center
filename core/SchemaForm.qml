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
    signal patchChanged(var patch)
    signal requestDeleteKey(string key)

    spacing: Style.spacing.panelGap

    function fieldTypeAt(index) {
        return index >= 0 && index < fields.length ? String(fields[index].type || "") : ""
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
                var patch = ({})
                patch[key] = value
                root.valueChanged(key, value)
                root.patchChanged(patch)
            }
            onRequestDeleteKey: function(key) {
                if (!root.readOnly) root.requestDeleteKey(key)
            }
        }
    }
}
