import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

Ui.BorderSurface {
    id: root
    property string filePath: "~/.config/omarchy/extensions/omarchy-menu.jsonc"
    property string state: "malformed"
    property string detail: "The menu file cannot be edited safely."
    signal replaceRequested()
    signal reloadRequested()
    color: Style.normalFill
    radius: Style.cornerRadius
    borderSpec: Border.controlSpec("normal", Color.foreground, Color.accent, Color.urgent)
    implicitHeight: form.implicitHeight + Style.spacing.panelPadding * 2

    ColumnLayout {
        id: form
        anchors.fill: parent
        anchors.margins: Style.spacing.panelPadding
        spacing: Style.spacing.lg
        Text { text: root.state === "unsupported" ? "Unsupported menu configuration" : "Menu file recovery"; color: Color.urgent; font.family: Style.font.family; font.pixelSize: Style.font.heading; font.bold: true }
        Text { Layout.fillWidth: true; text: root.filePath; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; wrapMode: Text.WrapAnywhere }
        Text { Layout.fillWidth: true; text: root.detail + " The setting is personal menu entries. Fix the file externally, then Reload, or replace it after an exact backup."; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; wrapMode: Text.WordWrap }
        RowLayout {
            Ui.Button { text: "Reload"; bordered: true; focusable: true; onClicked: root.reloadRequested() }
            Ui.Button { id: replaceButton; text: root.state === "duplicate-keys" ? "Keep last occurrences and continue" : "Replace after backup"; bordered: true; focusable: true; enabled: root.state !== "unsupported"; onClicked: root.replaceRequested() }
        }
    }
    function focusFirst() { replaceButton.forceActiveFocus() }
}
