import QtQuick
import qs.Commons
import qs.Ui as Ui

Ui.BorderSurface {
    id: root
    property var choice: null
    visible: choice !== null
    implicitHeight: details.implicitHeight + Style.spacing.md * 2
    color: Style.normalFill
    borderSpec: Border.controlSpec("normal", Color.foreground, Color.accent)

    Column {
        id: details
        anchors.fill: parent
        anchors.margins: Style.spacing.md
        spacing: Style.spacing.xs
        Text { text: root.choice ? "Command: " + (root.choice.command || root.choice.misePackage || "selector") : ""; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
        Text { text: root.choice && root.choice.desktopId ? "Desktop file: " + root.choice.desktopId : "Package integration: selector owned"; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
        Text { width: parent.width; text: root.choice && root.choice.installer ? root.choice.installer.summary + (root.choice.installer.needsSudo ? " Sudo may prompt." : "") + (root.choice.installer.launchesApp ? " An application opens." : "") : ""; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall; wrapMode: Text.WordWrap }
    }
}
