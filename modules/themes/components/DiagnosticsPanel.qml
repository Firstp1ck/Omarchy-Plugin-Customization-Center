import QtQuick
import QtQuick.Layouts
import qs.Commons

ColumnLayout {
    id: root
    property var payload: null
    property string errorText: ""
    spacing: Style.spacing.md
    Text { text: "Diagnostics"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.title; font.bold: true }
    Text { Layout.fillWidth: true; text: root.errorText.length ? "Preview unavailable: " + root.errorText + ". File: colors.toml. Setting: palette syntax. Recovery: correct the highlighted value and retry." : "Contrast checks compare text, surfaces, controls, and border stops. Masked machine overrides are listed by validation."; color: root.errorText.length ? Color.urgent : Color.muted; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.body }
}
