import QtQuick
import QtQuick.Layouts
import qs.Commons
RowLayout { id: root; property var palette: ({}); spacing: Style.spacing.sm; Repeater { model: 3; delegate: Rectangle { required property int index; Layout.preferredWidth: Style.space(70); Layout.preferredHeight: Style.space(110); color: index === 1 ? root.palette.accent : root.palette.background; border.color: root.palette.foreground; border.width: 1 } } }
