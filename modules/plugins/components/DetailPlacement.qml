import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

ColumnLayout {
    id: root
    property var row: null
    signal navigateRequested(var payload)
    spacing: Style.spacing.md
    Text { text: "Placement"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle }
    Text {
        Layout.fillWidth: true; wrapMode: Text.WordWrap; color: Color.foreground; font.family: Style.font.family
        text: !root.row ? "Select a plugin" : (root.row.kinds || []).indexOf("bar") >= 0
            ? "Configured bar: " + root.row.state.configuredBar + "\nRunning bar: " + root.row.state.runningBar
            : (root.row.instances || []).length === 0 ? "Not placed on the bar."
            : root.row.instances.map(function(item) { return item.section + "[" + item.index + "] " + JSON.stringify(item.entry) }).join("\n")
    }
    Text { Layout.fillWidth: true; visible: !!root.row && (root.row.instances || []).length > 1; text: root.row ? root.row.instances.length + " instances; settings show the first instance." : ""; color: Color.muted; font.family: Style.font.family }
    Ui.Button {
        objectName: "editInBarButton"
        visible: !!root.row && root.row.ownership === "bar"
        text: root.row && (root.row.kinds || []).indexOf("bar-widget") >= 0 && (root.row.instances || []).length === 0 ? "Add to bar in bar editor" : "Edit in bar editor"
        focusable: true
        onClicked: {
            if (!root.row) return
            if ((root.row.kinds || []).indexOf("bar") >= 0) root.navigateRequested({ selectBar: root.row.id })
            else if ((root.row.instances || []).length) root.navigateRequested({ select: { section: root.row.instances[0].section, index: root.row.instances[0].index } })
            else root.navigateRequested({ addWidget: root.row.id })
        }
    }
}
