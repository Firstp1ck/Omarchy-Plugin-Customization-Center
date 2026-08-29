import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

RowLayout {
    id: root
    property string label: "Border width"
    property string value: "1"
    signal valueRequested(string value)
    spacing: Style.spacing.sm
    Text { text: root.label; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
    Ui.TextField { Layout.fillWidth: true; text: root.value; placeholderText: "1 or 2 2 2 4"; onEditingFinished: root.valueRequested(text) }
}
