import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

Ui.BorderSurface {
    id: root
    property var palette: ({})
    width: Style.space(260); height: Style.space(220)
    color: root.palette.background
    borderSpec: Border.withWidth(Border.resolvedGradient(root.palette.accent, root.palette.accent, 1), "1")
    ColumnLayout {
        anchors.fill: parent; anchors.margins: Style.spacing.lg; spacing: Style.spacing.sm
        Text { text: "Theme menu"; color: root.palette.foreground; font.family: Style.font.family; font.pixelSize: Style.font.title; font.bold: true }
        Repeater { model: ["Normal row", "Selected row", "Disabled row"]; delegate: Rectangle { required property string modelData; Layout.fillWidth: true; Layout.preferredHeight: Style.spacing.popupRowHeight; color: modelData === "Selected row" ? root.palette.foreground : "transparent"; opacity: modelData === "Selected row" ? .85 : 1; Text { anchors.centerIn: parent; text: modelData; color: modelData === "Selected row" ? root.palette.accent : root.palette.foreground; opacity: modelData === "Disabled row" ? .5 : 1; font.family: Style.font.family; font.pixelSize: Style.font.body } } }
    }
}
