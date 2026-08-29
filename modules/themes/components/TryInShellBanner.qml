import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

Ui.BorderSurface {
    id: root
    property string transactionId: ""
    property bool outdated: false
    signal stopRequested()
    signal updateRequested()
    color: Color.notifications.background
    borderSpec: Border.surfaceSpec("notifications", "border")
    implicitHeight: row.implicitHeight + Style.spacing.lg * 2
    RowLayout {
        id: row; anchors.fill: parent; anchors.margins: Style.spacing.lg; spacing: Style.spacing.md
        Text { Layout.fillWidth: true; text: root.outdated ? "Shell preview is active but the draft changed." : "Shell preview is active. Transaction " + root.transactionId; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
        Ui.Button { visible: root.outdated; text: "Update preview"; focusable: true; onClicked: root.updateRequested() }
        Ui.Button { text: "Stop preview"; focusable: true; onClicked: root.stopRequested() }
    }
}
