import QtQuick
import QtQuick.Layouts
import qs.Commons

FocusScope {
    id: root
    property var modeRow: ({})
    property bool selected: false
    signal selectedRequested()
    signal openRequested()
    implicitHeight: body.implicitHeight + Style.spacing.md * 2
    activeFocusOnTab: true
    Rectangle { anchors.fill: parent; radius: Style.cornerRadius; color: root.selected ? Color.accent : Color.background; border.width: 1; border.color: root.activeFocus ? Color.accent : Color.muted }
    RowLayout { id: body; anchors.fill: parent; anchors.margins: Style.spacing.md; spacing: Style.spacing.md
        Text { text: root.modeRow.mode ? (root.modeRow.mode.icon || "󰒓") : "󰒓"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading }
        ColumnLayout { Layout.fillWidth: true; spacing: Style.spacing.xs
            Text { Layout.fillWidth: true; text: root.modeRow.mode ? root.modeRow.mode.name : ""; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; elide: Text.ElideRight }
            Text { Layout.fillWidth: true; text: root.modeRow.state || "never-applied"; color: root.modeRow.state === "drifted" || root.modeRow.state === "indeterminate" ? Color.urgent : Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption }
            Text { Layout.fillWidth: true; visible: root.modeRow.definitionChanged === true; text: "Definition changed since last apply"; color: Color.urgent; font.family: Style.font.family; font.pixelSize: Style.font.caption }
        }
    }
    TapHandler { onTapped: { root.forceActiveFocus(); root.selectedRequested() } }
    TapHandler { acceptedButtons: Qt.LeftButton; gesturePolicy: TapHandler.WithinBounds; onDoubleTapped: root.openRequested() }
    Keys.onPressed: function(event) { if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) { root.openRequested(); event.accepted = true } }
}
