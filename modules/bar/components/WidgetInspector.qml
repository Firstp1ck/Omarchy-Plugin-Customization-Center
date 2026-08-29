import QtQuick
import QtQuick.Layouts
import qs.Commons
import "../../../core" as Core

FocusScope {
    id: root
    property var entry: null
    property var catalogItem: null
    property bool busy: false
    signal settingChanged(string key, var value)
    signal removeRequested()
    ColumnLayout {
        anchors.fill: parent; spacing: Style.spacing.md
        Text { text: root.entry ? (root.catalogItem ? root.catalogItem.displayName : root.entry.id) : "Select a widget"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle }
        Text { visible: !!root.entry; text: root.entry ? root.entry.id : ""; color: Color.muted; font.family: Style.font.family }
        Core.SchemaForm { Layout.fillWidth: true; visible: !!root.entry; schema: root.catalogItem ? root.catalogItem.schema : ({ fields: [] }); values: root.entry ? root.entry.settings : ({}); readOnly: root.busy || !root.catalogItem || root.catalogItem.schema.ok !== true; onValueChanged: (key, value) => root.settingChanged(key, value) }
        Text { visible: root.entry && (!root.catalogItem || root.catalogItem.schema.ok !== true); text: "Preserved settings are read-only because no supported schema is available."; wrapMode: Text.WordWrap; color: Color.muted; font.family: Style.font.family }
    }
}
