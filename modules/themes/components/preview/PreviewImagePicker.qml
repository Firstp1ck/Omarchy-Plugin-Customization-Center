import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons
Item {
    id: root
    property var tokens: ({})
    readonly property var section: (tokens.sections || ({}))["image-picker"] || ({})
    width: 250; height: 150
    Rectangle { anchors.fill: parent; color: root.section.scrim + Math.round(Number(root.section["scrim-alpha"] || .5) * 255).toString(16).padStart(2, "0") }
    RowLayout { anchors.centerIn: parent; spacing: root.tokens.metrics.spacing.sm; Repeater { model: 3; delegate: Ui.BorderSurface { required property int index; Layout.preferredWidth: 70; Layout.preferredHeight: 110; color: root.tokens.palette.background; readonly property var spec: index === 1 ? root.tokens.borders["image-picker"]["selected-border"] : root.tokens.borders["image-picker"]["unselected-border"]; borderSpec: Border.withWidth(Border.resolvedGradient(spec.raw, root.tokens.palette.accent, spec.alpha), spec.width) } } }
    Text { anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; text: "Choose image"; color: root.section.text; font.family: Style.font.family; font.pixelSize: root.tokens.metrics.font.body }
}
