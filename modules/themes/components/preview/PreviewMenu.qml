import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

Ui.BorderSurface {
    id: root
    property var tokens: ({})
    property string sectionName: "menu"
    readonly property var section: (tokens.sections || ({}))[sectionName] || ({})
    readonly property var metrics: tokens.metrics || ({ spacing: {}, font: {} })
    readonly property var border: ((tokens.borders || ({}))[sectionName] || ({})).border || ({ raw: tokens.palette ? tokens.palette.accent : "#ffffff", width: "1", alpha: 1 })
    width: 260; height: 220
    color: section["background-composed"] || section.background || "#000000"
    borderSpec: Border.withWidth(Border.resolvedGradient(border.raw, tokens.palette ? tokens.palette.accent : "#ffffff", border.alpha), border.width)
    ColumnLayout {
        anchors.fill: parent; anchors.margins: root.metrics.spacing ? root.metrics.spacing.lg : 8; spacing: root.metrics.spacing ? root.metrics.spacing.sm : 4
        Text { text: root.sectionName === "launcher" ? "Theme launcher" : "Theme menu"; color: root.section.text; font.family: Style.font.family; font.pixelSize: root.metrics.font ? root.metrics.font.title : 14; font.bold: true }
        Repeater {
            model: ["Normal row", "Selected row", "Disabled row"]
            delegate: Rectangle {
                required property string modelData
                Layout.fillWidth: true; Layout.preferredHeight: root.metrics.spacing ? root.metrics.spacing["popup-row-height"] : 28
                color: modelData === "Selected row" ? (root.section["selected-background-composed"] || root.section["selected-background"]) : "transparent"
                Text { anchors.centerIn: parent; text: modelData; color: modelData === "Selected row" ? root.section["selected-text"] : root.section.text; opacity: modelData === "Disabled row" ? .5 : 1; font.family: Style.font.family; font.pixelSize: root.metrics.font ? root.metrics.font.body : 12 }
            }
        }
    }
}
