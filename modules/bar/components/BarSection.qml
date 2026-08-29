import QtQuick
import QtQuick.Layouts
import qs.Commons
import "." as Bar

FocusScope {
    id: root
    property string section: "left"
    property var entries: []
    property var catalog: []
    property string selectedKey: ""
    signal selected(string key)
    signal removeRequested(string key)
    signal moveRequested(string key, string section, int index)
    implicitHeight: Math.max(Style.spacing.controlHeight, row.implicitHeight)
    function labelFor(id) { for (var i = 0; i < catalog.length; ++i) if (catalog[i].id === id) return catalog[i].displayName; return id }
    RowLayout {
        id: row; anchors.fill: parent; spacing: Style.spacing.xs
        Text { visible: root.entries.length === 0; text: "Empty " + root.section; color: Color.muted; font.family: Style.font.family }
        Repeater {
            model: root.entries
            delegate: Bar.WidgetCard {
                required property var modelData
                entry: modelData; label: root.labelFor(modelData.id); selected: root.selectedKey === modelData.key
                onActivated: root.selected(modelData.key)
                onRemoveRequested: root.removeRequested(modelData.key)
                onBeginDrag: root.moveRequested(modelData.key, root.section, index)
            }
        }
    }
}
