import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

ColumnLayout {
    id: root
    property var tokens: ({})
    readonly property var section: (tokens.sections || ({})).lock || ({})
    readonly property var borders: (tokens.borders || ({})).lock || ({})
    readonly property var metrics: tokens.metrics || ({ spacing: {}, font: {} })
    spacing: metrics.spacing ? metrics.spacing.md : 6
    Repeater {
        model: ["Idle", "Active", "Error"]
        delegate: Ui.BorderSurface {
            required property string modelData
            readonly property string borderKey: modelData === "Error" ? "border-error" : modelData === "Active" ? "border-active" : "border"
            readonly property var spec: root.borders[borderKey] || ({ raw: root.tokens.palette ? root.tokens.palette.accent : "#ffffff", width: "1", alpha: 1 })
            Layout.preferredWidth: 240; Layout.preferredHeight: root.metrics.spacing ? root.metrics.spacing["control-height"] : 28
            color: root.section["background-composed"] || root.section.background
            borderSpec: Border.withWidth(Border.resolvedGradient(spec.raw, root.tokens.palette ? root.tokens.palette.accent : "#ffffff", spec.alpha), spec.width)
            Text { anchors.centerIn: parent; text: modelData === "Idle" ? root.section.placeholder : modelData + " password field"; color: modelData === "Error" ? root.section["text-error"] : root.section.text; font.family: Style.font.family; font.pixelSize: root.metrics.font ? root.metrics.font.body : 12 }
        }
    }
}
