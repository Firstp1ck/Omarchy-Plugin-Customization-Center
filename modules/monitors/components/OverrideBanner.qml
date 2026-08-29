import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

Ui.BorderSurface {
    id: root
    property string title: "Monitor configuration needs attention"
    property string fileName: "~/.config/hypr/monitors.lua"
    property string setting: "hl.monitor"
    property string recoveryAction: "Open the file, fix the setting, then rescan"
    property string actionLabel: "Rescan"
    signal actionRequested()
    color: Style.normalFillFor(Color.urgent, Color.accent)
    borderSpec: Border.controlSpec("focus", Color.urgent, Color.accent)
    implicitHeight: row.implicitHeight + Style.spacing.rowPaddingX * 2
    RowLayout {
        id: row; anchors.fill: parent; anchors.margins: Style.spacing.rowPaddingX; spacing: Style.spacing.md
        ColumnLayout {
            Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: root.title; color: Color.urgent; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true; wrapMode: Text.WordWrap }
            Text { Layout.fillWidth: true; text: root.fileName + " · " + root.setting + " · " + root.recoveryAction; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap }
        }
        Ui.Button { text: root.actionLabel; bordered: true; focusable: true; onClicked: root.actionRequested() }
    }
}
