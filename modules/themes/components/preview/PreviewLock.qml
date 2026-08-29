import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

ColumnLayout {
    id: root
    property var palette: ({})
    spacing: Style.spacing.md
    Repeater {
        model: ["Idle", "Active", "Error"]
        delegate: Ui.BorderSurface {
            required property string modelData
            Layout.preferredWidth: Style.space(240); Layout.preferredHeight: Style.spacing.controlHeight
            color: root.palette.background
            borderSpec: Border.withWidth(Border.resolvedGradient(modelData === "Error" ? root.palette.red : root.palette.accent, root.palette.accent, 1), "1")
            Text { anchors.centerIn: parent; text: modelData + " password field"; color: modelData === "Error" ? root.palette.red : root.palette.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
        }
    }
}
