import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons
import "preview"

Ui.BorderSurface {
    id: root
    property var payload: null
    property bool loading: false
    property string errorText: ""
    property string scenario: "controls"
    property real zoom: 1.0
    color: Color.background
    borderSpec: Border.surfaceSpec("popups", "border")

    readonly property var palette: payload && payload.tokens && payload.tokens.palette ? payload.tokens.palette : ({ background: Color.background, foreground: Color.foreground, accent: Color.accent, red: Color.urgent })

    ColumnLayout {
        anchors.fill: parent; anchors.margins: Style.spacing.md; spacing: Style.spacing.sm
        Text { Layout.fillWidth: true; text: "Representative preview. Use Try in shell for the live shell."; color: Color.muted; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.caption }
        RowLayout {
            Layout.fillWidth: true
            Ui.Button { text: "Controls"; focusable: true; selected: root.scenario === "controls"; onClicked: root.scenario = "controls" }
            Ui.Button { text: "Menu"; focusable: true; selected: root.scenario === "menu"; onClicked: root.scenario = "menu" }
            Ui.Button { text: "Lock"; focusable: true; selected: root.scenario === "lock"; onClicked: root.scenario = "lock" }
            Item { Layout.fillWidth: true }
            Ui.Button { text: root.zoom + "x"; focusable: true; onClicked: root.zoom = root.zoom === 1 ? 1.5 : root.zoom === 1.5 ? 2 : 1 }
        }
        Text { visible: root.loading; text: "Rendering preview…"; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
        Text { Layout.fillWidth: true; visible: root.errorText.length > 0; text: "Preview unavailable: " + root.errorText + ". File: shell.toml. Setting: preview tokens. Recovery: fix the draft and retry."; color: Color.urgent; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.body }
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            color: root.palette.background
            Loader {
                anchors.centerIn: parent
                width: parent.width / root.zoom
                height: parent.height / root.zoom
                scale: root.zoom
                sourceComponent: root.scenario === "menu" ? menuPreview : root.scenario === "lock" ? lockPreview : controlsPreview
            }
        }
    }
    Component { id: controlsPreview; PreviewControls { palette: root.palette } }
    Component { id: menuPreview; PreviewMenu { palette: root.palette } }
    Component { id: lockPreview; PreviewLock { palette: root.palette } }
}
