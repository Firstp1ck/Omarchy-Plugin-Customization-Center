import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

ColumnLayout {
    id: root
    property var modes: []
    property var value: null
    property bool stale: false
    signal modeSelected(var mode)
    spacing: Style.spacing.md

    function groupedModes() {
        var groups = []
        var byResolution = ({})
        for (var i = 0; i < modes.length; ++i) {
            var mode = modes[i]
            var key = mode.width + "×" + mode.height
            if (!byResolution[key]) {
                byResolution[key] = { label: key, modes: [] }
                groups.push(byResolution[key])
            }
            byResolution[key].modes.push(mode)
        }
        return groups
    }

    Text { text: "Mode" + (root.stale ? " · stale cache" : ""); color: root.stale ? Color.urgent : Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
    Repeater {
        model: root.groupedModes()
        delegate: ColumnLayout {
            id: groupColumn
            required property var modelData
            Text { text: modelData.label; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption }
            RowLayout {
                Repeater {
                    model: groupColumn.modelData.modes
                    delegate: Ui.Button {
                        required property var modelData
                        objectName: "mode-" + modelData.width + "x" + modelData.height + "-" + modelData.refreshMilliHz
                        text: (modelData.refreshMilliHz / 1000) + " Hz"
                        selected: root.value && root.value.width === modelData.width && root.value.height === modelData.height && root.value.refreshMilliHz === modelData.refreshMilliHz
                        bordered: true; focusable: true
                        onClicked: root.modeSelected(modelData)
                    }
                }
            }
        }
    }
    Text { visible: !root.modes || root.modes.length === 0; text: "No modes from hyprctl monitors all. Reconnect the output and retry before changing the mode setting."; color: Color.muted; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.caption }
}
