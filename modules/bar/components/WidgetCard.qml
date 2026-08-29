import QtQuick
import qs.Commons

FocusScope {
    id: root
    property var entry: ({})
    property string label: entry.id || "Unknown"
    property bool selected: false
    property bool grabbed: false
    signal activated()
    signal beginDrag()
    signal removeRequested()
    implicitWidth: 92; implicitHeight: Style.spacing.controlHeight
    activeFocusOnTab: true
    Keys.onSpacePressed: { activated(); event.accepted = true }
    Keys.onReturnPressed: { activated(); event.accepted = true }
    Keys.onDeletePressed: { removeRequested(); event.accepted = true }
    Rectangle { anchors.fill: parent; color: root.selected ? Color.accent : Style.normalFill; border.color: root.activeFocus || root.grabbed ? Color.accent : Color.muted; border.width: Style.normalBorderWidth }
    Text { anchors.centerIn: parent; width: parent.width - Style.spacing.md * 2; elide: Text.ElideRight; text: root.label; color: root.selected ? Color.background : Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
    MouseArea { anchors.fill: parent; hoverEnabled: true; onClicked: root.activated(); onPressAndHold: root.beginDrag() }
}
