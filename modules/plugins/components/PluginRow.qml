import QtQuick
import QtQuick.Layouts
import qs.Commons

FocusScope {
    id: root
    property var row: ({})
    property bool selected: false
    signal selectedRequested()
    signal actionMenuRequested()
    implicitHeight: content.implicitHeight + Style.spacing.md * 2
    activeFocusOnTab: true

    Rectangle {
        anchors.fill: parent
        radius: Style.cornerRadius
        color: root.selected ? Color.accent : Color.background
        border.color: root.activeFocus ? Color.accent : Color.muted
        border.width: 1
    }
    RowLayout {
        id: content
        anchors.fill: parent
        anchors.margins: Style.spacing.md
        spacing: Style.spacing.md
        ColumnLayout {
            Layout.fillWidth: true
            spacing: Style.spacing.xs
            Text { Layout.fillWidth: true; text: root.row.name || root.row.id || ""; elide: Text.ElideRight; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle }
            Text { Layout.fillWidth: true; text: (root.row.id || "") + "  " + (root.row.kinds || []).join(", "); elide: Text.ElideRight; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption }
        }
        OriginChip { row: root.row }
        StateChip { row: root.row }
    }
    TapHandler { onTapped: { root.forceActiveFocus(); root.selectedRequested() } }
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) { root.selectedRequested(); event.accepted = true }
        else if (event.key === Qt.Key_Menu || (event.key === Qt.Key_F10 && (event.modifiers & Qt.ShiftModifier))) { root.actionMenuRequested(); event.accepted = true }
    }
}
