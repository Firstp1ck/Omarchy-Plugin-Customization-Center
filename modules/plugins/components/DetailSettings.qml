import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui
import "../../../core" as Core

ColumnLayout {
    id: root
    property var row: null
    signal navigateRequested(var payload)
    spacing: Style.spacing.md
    readonly property var settings: row && row.settings ? row.settings : ({ fields: [], support: "none", problems: [] })
    readonly property var values: row && row.instances && row.instances.length ? row.instances[0].entry : ({})
    Text { text: "Settings metadata"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle }
    Text { Layout.fillWidth: true; visible: root.settings.adapterId !== null && root.settings.adapterId !== undefined; text: "Built-in " + root.settings.adapterId + " settings, stored on the bar entry."; color: Color.muted; font.family: Style.font.family }
    Core.SchemaForm { objectName: "readOnlySettingsForm"; Layout.fillWidth: true; schema: root.settings; values: root.values; readOnly: true }
    Text { Layout.fillWidth: true; visible: root.settings.support === "none"; text: "No declared settings metadata."; color: Color.muted; font.family: Style.font.family }
    Repeater {
        model: root.settings.problems || []
        Text { required property var modelData; Layout.fillWidth: true; wrapMode: Text.WordWrap; text: modelData.code + ": " + modelData.message; color: Color.urgent; font.family: Style.font.family }
    }
    Text { Layout.fillWidth: true; visible: !!root.settings.extension && root.row && root.row.ownership === "plugins"; wrapMode: Text.WordWrap; text: "No write path for plugins[] settings exists in this Omarchy version. Metadata is read-only."; color: Color.muted; font.family: Style.font.family }
    Ui.Button {
        visible: !!root.row && root.row.ownership === "bar"
        text: "Edit in bar editor"
        focusable: true
        onClicked: {
            if ((root.row.kinds || []).indexOf("bar") >= 0) root.navigateRequested({ selectBar: root.row.id })
            else if ((root.row.instances || []).length) root.navigateRequested({ select: { section: root.row.instances[0].section, index: root.row.instances[0].index } })
            else root.navigateRequested({ addWidget: root.row.id })
        }
    }
}
