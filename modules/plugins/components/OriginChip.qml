import QtQuick
import qs.Commons

Rectangle {
    id: root
    property var row: ({})
    readonly property string label: row.origin && row.origin.class === "user-clone" ? "Clone of " + (row.clonedFrom || "unknown")
        : row.firstParty ? "Omarchy" : "Installed"
    implicitWidth: textItem.implicitWidth + Style.spacing.md * 2
    implicitHeight: textItem.implicitHeight + Style.spacing.xs * 2
    radius: Style.cornerRadius
    color: Color.background
    border.color: Color.muted
    border.width: 1
    Text { id: textItem; anchors.centerIn: parent; text: root.label; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.caption }
}
