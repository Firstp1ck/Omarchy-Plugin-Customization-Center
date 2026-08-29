import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

ColumnLayout {
    id: root
    property string label: "Gradient"
    property var value: null
    signal valueRequested(var value)
    spacing: Style.spacing.xs
    Text { text: root.label; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
    Ui.TextField {
        Layout.fillWidth: true
        text: root.value || ""
        placeholderText: "rgba(rrggbbaa) rgba(rrggbbaa) 45deg"
        Accessible.name: root.label
        onEditingFinished: root.valueRequested(text.length ? text : null)
    }
}
