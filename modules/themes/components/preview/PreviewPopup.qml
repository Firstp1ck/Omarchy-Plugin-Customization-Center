import QtQuick
import qs.Ui as Ui
import qs.Commons
Ui.BorderSurface { id: root; property var palette: ({}); color: root.palette.background; borderSpec: Border.withWidth(Border.resolvedGradient(root.palette.accent, root.palette.accent, 1), "1"); implicitWidth: Style.space(220); implicitHeight: Style.space(120); Text { anchors.centerIn: parent; text: "Popup and tooltip"; color: root.palette.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body } }
