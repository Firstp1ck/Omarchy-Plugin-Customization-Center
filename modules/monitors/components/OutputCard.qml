import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

Ui.BorderSurface {
    id: root
    property var output: null
    property bool selected: false
    signal activated()
    color: selected ? Style.selectionFill : Color.popups.background
    borderSpec: Border.controlSpec(activeFocus ? "focus" : (selected ? "selected" : "normal"), Color.foreground, Color.accent)
    implicitHeight: content.implicitHeight + Style.spacing.rowPaddingX * 2
    focus: true
    ColumnLayout {
        id: content; anchors.fill: parent; anchors.margins: Style.spacing.rowPaddingX
        Text { text: root.output ? (root.output.label || root.output.connector || "Output") : "Output unavailable"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
        Text { Layout.fillWidth: true; text: root.output ? ((root.output.identity ? root.output.identity.connector : root.output.connector) + " · scale120 " + (root.output.scale120 || "unknown")) : "monitors.lua output setting is unavailable; retry inventory to recover"; color: Color.muted; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.caption }
    }
    MouseArea { anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: { root.forceActiveFocus(); root.activated() } }
    Keys.onReturnPressed: activated()
    Keys.onSpacePressed: activated()
}
