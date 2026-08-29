import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

RowLayout {
    id: root
    property var handoffs: []
    signal abandonRequested(string transactionId)
    visible: handoffs.length > 0
    spacing: Style.spacing.md
    Text { Layout.fillWidth: true; text: root.handoffs.length ? "Waiting for terminal: " + (root.handoffs[0].action || "plugin action") + (root.handoffs[0].pluginId ? " " + root.handoffs[0].pluginId : "") + ". No success is claimed until reconciliation." : ""; color: Color.foreground; font.family: Style.font.family; wrapMode: Text.WordWrap }
    Ui.Button { text: "Dismiss"; focusable: true; enabled: root.handoffs.length > 0; onClicked: if (root.handoffs.length) root.abandonRequested(root.handoffs[0].transactionId) }
}
