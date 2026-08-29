import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

ColumnLayout {
    id: root
    property var tokens: ({})
    readonly property var metrics: tokens.metrics || ({ spacing: {}, font: {} })
    spacing: metrics.spacing ? metrics.spacing.md || 6 : 6
    function stateToken(label) { return (tokens.controls || ({}))[label] || ({ color: "#ffffff", fill: "#00000000", border: { raw: "#ffffff", width: "1", alpha: 1 } }) }
    Repeater {
        model: ["normal", "hover-cursor", "focus", "selected"]
        delegate: Ui.BorderSurface {
            required property string modelData
            readonly property var state: root.stateToken(modelData)
            Layout.preferredWidth: 220; Layout.preferredHeight: root.metrics.spacing ? root.metrics.spacing["control-height"] : 28
            color: state.fill
            borderSpec: Border.withWidth(Border.resolvedGradient(state.border.raw, state.color, state.border.alpha), state.border.width)
            Text { anchors.centerIn: parent; text: modelData + " control"; color: parent.state.color; font.family: Style.font.family; font.pixelSize: root.metrics.font ? root.metrics.font.body : 12 }
        }
    }
    Ui.BorderSurface {
        readonly property var state: root.stateToken("normal")
        Layout.preferredWidth: 220; Layout.preferredHeight: root.metrics.spacing ? root.metrics.spacing["control-height"] : 28
        color: state.color + Math.round((root.tokens.controls ? root.tokens.controls.pressedFillAlpha : .22) * 255).toString(16).padStart(2, "0")
        borderSpec: Border.withWidth(Border.resolvedGradient(state.border.raw, state.color, state.border.alpha), state.border.width)
        Text { anchors.centerIn: parent; text: "pressed control"; color: parent.state.color; font.family: Style.font.family; font.pixelSize: root.metrics.font ? root.metrics.font.body : 12 }
    }
}
