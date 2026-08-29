import QtQuick
import qs.Commons
import qs.Ui as Ui

Ui.BorderSurface {
    id: root
    property string text: ""
    implicitWidth: label.implicitWidth + Style.spacing.md * 2
    implicitHeight: label.implicitHeight + Style.spacing.xs * 2
    color: Style.hoverFill
    radius: Style.cornerRadius
    borderSpec: Border.controlSpec("normal", Color.foreground, Color.accent)

    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        color: Color.muted
        font.family: Style.font.family
        font.pixelSize: Style.font.caption
    }
}
