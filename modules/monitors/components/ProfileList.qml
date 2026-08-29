import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

Ui.BorderSurface {
    id: root
    property var profiles: []
    property string selectedId: ""
    signal selected(string profileId)
    color: Color.popups.background
    borderSpec: Border.controlSpec("normal", Color.foreground, Color.accent)
    implicitWidth: Style.space(220)
    implicitHeight: list.implicitHeight + Style.spacing.rowPaddingX * 2

    ColumnLayout {
        id: list
        anchors.fill: parent
        anchors.margins: Style.spacing.rowPaddingX
        spacing: Style.spacing.md
        Text { text: "Profiles"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; font.bold: true }
        Repeater {
            model: root.profiles || []
            delegate: Ui.Button {
                required property var modelData
                Layout.fillWidth: true
                text: modelData.name + " · " + (modelData.fit ? modelData.fit.state : "unknown")
                selected: root.selectedId === modelData.id
                bordered: true
                focusable: true
                onClicked: root.selected(modelData.id)
            }
        }
        Text {
            Layout.fillWidth: true
            visible: !root.profiles || root.profiles.length === 0
            text: "No profiles in monitor-profiles/. Capture the current monitor setting to recover from this empty state."
            color: Color.muted; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall
        }
    }
}
