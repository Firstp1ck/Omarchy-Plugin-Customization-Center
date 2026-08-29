import QtQuick
import qs.Commons
Rectangle { id: root; property var palette: ({}); color: root.palette.background; implicitWidth: Style.space(280); implicitHeight: Style.spacing.controlHeight; Text { anchors.centerIn: parent; text: "1  2  3     12:00     active"; color: root.palette.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body } }
