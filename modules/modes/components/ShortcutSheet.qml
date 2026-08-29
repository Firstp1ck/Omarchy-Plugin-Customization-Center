import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

ColumnLayout {
    id: root
    property string command: ""
    signal keybindingRequested()
    signal menuRequested()
    Text { text: "Shortcut opens Review; it never applies automatically."; color: Color.foreground; font.family: Style.font.family; wrapMode: Text.WordWrap }
    Text { Layout.fillWidth: true; text: root.command; color: Color.muted; font.family: Style.font.family; wrapMode: Text.WrapAnywhere }
    RowLayout { Ui.Button { text: "Add keybinding"; onClicked: root.keybindingRequested() } Ui.Button { text: "Add menu entry"; onClicked: root.menuRequested() } }
}
