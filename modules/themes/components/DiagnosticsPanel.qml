import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

Flickable {
    id: root
    property var payload: null
    property string errorText: ""
    readonly property var contrast: payload && payload.contrast ? payload.contrast : []
    readonly property var masked: payload && payload.tokens && payload.tokens.masked ? payload.tokens.masked : []
    clip: true
    contentHeight: content.implicitHeight
    ColumnLayout {
        id: content; width: root.width; spacing: Style.spacing.md
        Text { text: "Diagnostics"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.title; font.bold: true }
        Text { Layout.fillWidth: true; text: root.errorText.length ? "Preview unavailable: " + root.errorText + ". Correct the highlighted draft value and retry." : "Contrast checks include composed surfaces, controls, border stops, and black/white bounds for translucent surfaces."; color: root.errorText.length ? Color.urgent : Color.muted; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.body }
        Repeater {
            model: root.contrast
            delegate: Ui.BorderSurface {
                required property var modelData
                Layout.fillWidth: true; implicitHeight: row.implicitHeight + Style.spacing.sm * 2
                color: Style.normalFill
                borderSpec: Border.controlSpec(modelData.blocked ? "focus" : modelData.passes ? "normal" : "selected", Color.foreground, modelData.blocked ? Color.urgent : Color.accent)
                RowLayout {
                    id: row; anchors.fill: parent; anchors.margins: Style.spacing.sm
                    Text { Layout.fillWidth: true; text: modelData.pairId + " · " + modelData.ratio + ":1 · " + (modelData.blocked ? "BLOCKED" : modelData.passes ? "pass" : "acknowledgement required"); color: modelData.blocked ? Color.urgent : modelData.passes ? Color.muted : Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall; wrapMode: Text.WordWrap }
                    Text { text: modelData.nearestPaletteKey ? "Try " + modelData.nearestPaletteKey : ""; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption }
                }
            }
        }
        Text { visible: root.masked.length > 0; text: "Masked by ~/.config/omarchy/shell.toml"; color: Color.urgent; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; font.bold: true }
        Repeater { model: root.masked; delegate: Text { required property var modelData; Layout.fillWidth: true; text: modelData.section + "." + modelData.key + ": draft " + modelData.draftValue + " → machine " + modelData.overrideValue; color: Color.muted; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall } }
    }
}
