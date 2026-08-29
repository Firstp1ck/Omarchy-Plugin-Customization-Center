import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

ColumnLayout {
    id: root
    property string label: "Condition"
    property string value: ""
    property string syntaxMessage: value ? "Syntax is checked by bash without running it." : "Not set"
    signal edited(string value)
    spacing: Style.spacing.xs

    Text { text: root.label; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
    Ui.TextField {
        Layout.fillWidth: true
        text: root.value
        placeholderText: "Bash command list"
        onTextEdited: root.edited(text)
    }
    Text {
        Layout.fillWidth: true
        text: root.syntaxMessage + " It runs on every menu open and shell reload."
        color: Color.muted
        font.family: Style.font.family
        font.pixelSize: Style.font.caption
        wrapMode: Text.WordWrap
    }
}
