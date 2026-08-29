import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

ColumnLayout {
    id: root
    property var palette: ({})
    spacing: Style.spacing.md
    Repeater {
        model: ["Normal", "Hover cursor", "Focus", "Selected", "Pressed"]
        delegate: Ui.BorderSurface {
            required property string modelData
            Layout.preferredWidth: Style.space(220); Layout.preferredHeight: Style.spacing.controlHeight
            color: root.palette.foreground
            opacity: modelData === "Selected" ? .85 : modelData === "Pressed" ? .95 : .72
            borderSpec: Border.withWidth(Border.resolvedGradient(root.palette.accent, root.palette.accent, 1), "1")
            Text { anchors.centerIn: parent; text: modelData + " control"; color: root.palette.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
        }
    }
}
