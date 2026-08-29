import QtQuick
import qs.Ui as Ui
import qs.Commons
Ui.BorderSurface {
    id: root
    property var tokens: ({})
    readonly property var section: (tokens.sections || ({})).polkit || ({})
    readonly property var spec: ((tokens.borders || ({})).polkit || ({})).border || ({ raw: tokens.palette ? tokens.palette.accent : "#fff", width: "1", alpha: 1 })
    color: section["background-composed"] || section.background
    borderSpec: Border.withWidth(Border.resolvedGradient(spec.raw, tokens.palette.accent, spec.alpha), spec.width)
    implicitWidth: 250; implicitHeight: 150
    Text { anchors.centerIn: parent; text: "Authentication required\nError sample"; color: root.section["text-error"]; horizontalAlignment: Text.AlignHCenter; font.family: Style.font.family; font.pixelSize: root.tokens.metrics.font.body }
}
