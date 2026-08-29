import QtQuick
import qs.Commons

Rectangle {
    id: root
    property var row: ({})
    readonly property string label: row.ownership === "bar"
        ? ((row.kinds || []).indexOf("bar") >= 0 ? (row.state && row.state.active ? "Bar in use" : "Available bar")
           : ((row.instances || []).length ? "On bar (" + row.instances.length + ")" : "Not on bar"))
        : (row.state && row.state.enabled ? "Enabled" : (row.firstParty ? "Switched off" : "Disabled"))
    implicitWidth: textItem.implicitWidth + Style.spacing.md * 2
    implicitHeight: textItem.implicitHeight + Style.spacing.xs * 2
    radius: Style.cornerRadius
    color: root.row.state && root.row.state.enabled ? Color.accent : Color.background
    border.color: Color.muted
    border.width: 1
    Text { id: textItem; anchors.centerIn: parent; text: root.label; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.caption }
}
