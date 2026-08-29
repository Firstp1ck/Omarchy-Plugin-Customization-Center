import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

ColumnLayout {
    id: root
    property string title: "Surface"
    property string message: ""
    property bool inherited: true
    signal inheritRequested(bool inherited)
    spacing: Style.spacing.md
    Text { text: root.title; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.title; font.bold: true }
    Ui.Toggle { Layout.fillWidth: true; label: "Inherit generated defaults"; description: "Turn off to write a complete shell.<section>.toml fragment."; checked: root.inherited; onClicked: root.inheritRequested(!root.inherited) }
    Text { Layout.fillWidth: true; text: root.message; color: Color.muted; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.body }
}
