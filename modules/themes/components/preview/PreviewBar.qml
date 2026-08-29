import QtQuick
import qs.Ui as Ui
import qs.Commons
Ui.BorderSurface {
    id: root
    property var tokens: ({})
    property bool vertical: false
    readonly property var section: (tokens.sections || ({})).bar || ({})
    readonly property var metrics: tokens.metrics || ({ bar: {}, font: {} })
    color: section["background-composed"] || section.background
    implicitWidth: vertical ? (metrics.bar.sizeVertical || 28) : 300
    implicitHeight: vertical ? 220 : (metrics.bar.sizeHorizontal || 26)
    borderSpec: Border.withWidth(Border.resolvedGradient(tokens.hyprland ? tokens.hyprland["active-border"] : tokens.palette.accent, tokens.palette.accent, 1), "1")
    Text { anchors.centerIn: parent; text: root.vertical ? "1\n2\n3\n12:00" : "1  2  3     12:00     active"; color: root.section.text; horizontalAlignment: Text.AlignHCenter; font.family: Style.font.family; font.pixelSize: root.metrics.font ? root.metrics.font.body : 12 }
}
