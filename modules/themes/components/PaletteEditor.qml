import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

Flickable {
    id: root
    property var draft: ({})
    property bool busy: false
    signal patchRequested(var patch)
    clip: true
    contentHeight: content.implicitHeight

    readonly property var keys: ["accent", "selection", "muted", "background", "dark_background", "darker_background", "lighter_background", "foreground", "dark_foreground", "light_foreground", "bright_foreground", "red", "yellow", "orange", "green", "cyan", "blue", "magenta", "brown", "bright_red", "bright_yellow", "bright_green", "bright_cyan", "bright_blue", "bright_magenta"]

    ColumnLayout {
        id: content
        width: root.width
        spacing: Style.spacing.md
        Text { text: "Palette"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.title; font.bold: true }
        RowLayout {
            Text { text: "Mode"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
            Ui.Button { text: "Dark"; focusable: true; selected: root.draft && root.draft.palette && root.draft.palette.mode === "dark"; enabled: !root.busy; onClicked: root.patchRequested({ palette: { mode: "dark" } }) }
            Ui.Button { text: "Light"; focusable: true; selected: root.draft && root.draft.palette && root.draft.palette.mode === "light"; enabled: !root.busy; onClicked: root.patchRequested({ palette: { mode: "light" } }) }
        }
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            rowSpacing: Style.spacing.sm
            columnSpacing: Style.spacing.md
            Repeater {
                model: root.keys
                delegate: RowLayout {
                    required property string modelData
                    Layout.fillWidth: true
                    spacing: Style.spacing.sm
                    Rectangle {
                        Layout.preferredWidth: Style.spacing.controlHeight
                        Layout.preferredHeight: Style.spacing.controlHeight
                        color: root.draft && root.draft.palette ? root.draft.palette[modelData] || Color.background : Color.background
                        border.color: Color.foreground
                        border.width: 1
                    }
                    Ui.TextField {
                        Layout.fillWidth: true
                        text: root.draft && root.draft.palette ? root.draft.palette[modelData] || "" : ""
                        placeholderText: "#rrggbb"
                        enabled: !root.busy
                        Accessible.name: modelData + ", " + text + ", palette color"
                        onEditingFinished: { var value = {}; value[modelData] = text; root.patchRequested({ palette: value }) }
                    }
                }
            }
        }
        GradientField { Layout.fillWidth: true; label: "Active Hyprland border"; value: root.draft && root.draft.palette ? root.draft.palette.hyprland_active_border : null; onValueRequested: value => root.patchRequested({ palette: { hyprland_active_border: value } }) }
        GradientField { Layout.fillWidth: true; label: "Inactive Hyprland border"; value: root.draft && root.draft.palette ? root.draft.palette.hyprland_inactive_border : null; onValueRequested: value => root.patchRequested({ palette: { hyprland_inactive_border: value } }) }
    }
}
