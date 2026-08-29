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
    property string backdrop: "theme"
    property real zoom: 1.0
    color: Color.background
    borderSpec: Border.surfaceSpec("popups", "border")

    readonly property var tokens: payload && payload.tokens ? payload.tokens : ({ palette: { background: Color.background, foreground: Color.foreground, accent: Color.accent, red: Color.urgent, muted: Color.muted }, sections: {}, borders: {}, metrics: { font: { body: 12 }, spacing: { md: 6, sm: 4 }, bar: {} }, controls: {} })
    readonly property var scenarios: [
        { value: "palette", label: "Palette" }, { value: "bar-horizontal", label: "Bar horizontal" }, { value: "bar-vertical", label: "Bar vertical" },
        { value: "controls", label: "Controls" }, { value: "popup", label: "Popup" }, { value: "tooltip", label: "Tooltip" },
        { value: "notification", label: "Notification" }, { value: "menu", label: "Menu" }, { value: "launcher", label: "Launcher" },
        { value: "lock", label: "Lock" }, { value: "polkit", label: "Polkit" }, { value: "image-picker", label: "Image picker" }, { value: "type", label: "Type and spacing" }
    ]
    function backdropColor() { return backdrop === "black" ? "#000000" : backdrop === "white" ? "#ffffff" : tokens.palette.background }

    ColumnLayout {
        anchors.fill: parent; anchors.margins: Style.spacing.md; spacing: Style.spacing.sm
        Text { Layout.fillWidth: true; text: "Representative preview. Use Try in shell for the live shell."; color: Color.muted; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.caption }
        RowLayout {
            Layout.fillWidth: true
            Ui.Dropdown { Layout.fillWidth: true; value: root.scenario; options: root.scenarios; onChanged: value => root.scenario = value }
            Ui.Dropdown { Layout.preferredWidth: Style.space(110); value: root.backdrop; options: [{value:"theme",label:"Theme"},{value:"black",label:"Black"},{value:"white",label:"White"}]; onChanged: value => root.backdrop = value }
            Ui.Button { text: root.zoom + "x"; focusable: true; Accessible.name: "Preview zoom"; onClicked: root.zoom = root.zoom === 1 ? 1.5 : root.zoom === 1.5 ? 2 : 1 }
        }
        Text { visible: root.loading; text: "Rendering preview…"; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.body }
        Text { Layout.fillWidth: true; visible: root.errorText.length > 0; text: "Preview unavailable: " + root.errorText + ". File: shell.toml. Setting: preview tokens. Recovery: fix the draft and retry."; color: Color.urgent; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.body }
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true; color: root.backdropColor()
            Loader {
                anchors.centerIn: parent; width: parent.width / root.zoom; height: parent.height / root.zoom; scale: root.zoom
                sourceComponent: root.scenario === "palette" ? palettePreview
                    : root.scenario === "bar-horizontal" || root.scenario === "bar-vertical" ? barPreview
                    : root.scenario === "menu" || root.scenario === "launcher" ? menuPreview
                    : root.scenario === "lock" ? lockPreview : root.scenario === "popup" || root.scenario === "tooltip" ? popupPreview
                    : root.scenario === "notification" ? notificationPreview : root.scenario === "polkit" ? polkitPreview
                    : root.scenario === "image-picker" ? pickerPreview : root.scenario === "type" ? typePreview : controlsPreview
            }
        }
    }
    Component { id: controlsPreview; PreviewControls { tokens: root.tokens } }
    Component { id: menuPreview; PreviewMenu { tokens: root.tokens; sectionName: root.scenario === "launcher" ? "launcher" : "menu" } }
    Component { id: lockPreview; PreviewLock { tokens: root.tokens } }
    Component { id: barPreview; PreviewBar { tokens: root.tokens; vertical: root.scenario === "bar-vertical" } }
    Component { id: popupPreview; PreviewPopup { tokens: root.tokens; sectionName: root.scenario === "tooltip" ? "tooltip" : "popups" } }
    Component { id: notificationPreview; PreviewNotification { tokens: root.tokens } }
    Component { id: polkitPreview; PreviewPolkit { tokens: root.tokens } }
    Component { id: pickerPreview; PreviewImagePicker { tokens: root.tokens } }
    Component { id: typePreview; PreviewType { tokens: root.tokens } }
    Component {
        id: palettePreview
        GridLayout {
            columns: 4
            Repeater {
                model: ["background","dark_background","darker_background","lighter_background","foreground","dark_foreground","light_foreground","bright_foreground","red","yellow","orange","green","cyan","blue","magenta","brown"]
                delegate: Rectangle { required property string modelData; Layout.preferredWidth: 62; Layout.preferredHeight: 48; color: root.tokens.palette[modelData]; Text { anchors.centerIn: parent; text: modelData.substring(0, 5); color: root.tokens.palette.foreground; font.family: Style.font.family; font.pixelSize: root.tokens.metrics.font.caption } }
            }
        }
    }
}
