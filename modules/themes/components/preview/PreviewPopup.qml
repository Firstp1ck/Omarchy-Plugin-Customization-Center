import QtQuick
import qs.Ui as Ui
import qs.Commons
Ui.BorderSurface {
    id: root
    property var tokens: ({})
    property string sectionName: "popups"
    readonly property var section: (tokens.sections || ({}))[sectionName] || ({})
    readonly property var spec: ((tokens.borders || ({}))[sectionName] || ({})).border || ({ raw: tokens.palette ? tokens.palette.accent : "#fff", width: "1", alpha: 1 })
    color: section["background-composed"] || section.background
    borderSpec: Border.withWidth(Border.resolvedGradient(spec.raw, tokens.palette.accent, spec.alpha), spec.width)
    implicitWidth: 220; implicitHeight: 120
    Text { anchors.centerIn: parent; text: root.sectionName === "tooltip" ? "Tooltip" : "Popup card"; color: root.section.text; font.family: Style.font.family; font.pixelSize: root.tokens.metrics.font.body }
}
