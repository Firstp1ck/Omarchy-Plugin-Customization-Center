import QtQuick
import qs.Ui as Ui
import qs.Commons
Ui.BorderSurface {
    id: root
    property var tokens: ({})
    readonly property var section: (tokens.sections || ({})).notifications || ({})
    readonly property var spec: ((tokens.borders || ({})).notifications || ({})).border || ({ raw: tokens.palette ? tokens.palette.accent : "#fff", width: "1", alpha: 1 })
    color: section["background-composed"] || section.background
    borderSpec: Border.withWidth(Border.resolvedGradient(spec.raw, tokens.palette.accent, spec.alpha), spec.width)
    implicitWidth: 260; implicitHeight: 100
    Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 4; color: root.section.countdown }
    Text { anchors.centerIn: parent; text: "Notification\nTheme saved"; color: root.section.text; horizontalAlignment: Text.AlignHCenter; font.family: Style.font.family; font.pixelSize: root.tokens.metrics.font.body }
    Text { objectName: "clipBadge"; anchors.right: parent.right; anchors.top: parent.top; text: "CLIP"; visible: root.tokens.metrics.font.body >= 40; color: root.tokens.palette.red; font.family: Style.font.family; font.pixelSize: root.tokens.metrics.font.caption }
}
