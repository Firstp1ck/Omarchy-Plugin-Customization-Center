import QtQuick
import qs.Commons
import qs.Ui as Ui

Ui.BorderSurface {
    id: root
    property var pending: null
    property var backendClient: null
    property string terminalHint: "Checking the Omarchy terminal window"
    readonly property bool canAbandon: backendClient && typeof backendClient.abandon === "function"
    signal recheck()
    signal abandon()
    implicitHeight: pendingColumn.implicitHeight + Style.spacing.md * 2
    color: Style.normalFillFor(Color.accent, Color.accent)
    borderSpec: Border.controlSpec("focus", Color.foreground, Color.accent)

    function refreshHint() {
        if (!backendClient) return
        backendClient.query("defaults", "terminal_windows", ({}), function(result) {
            var data = result && result.data ? result.data : null
            terminalHint = data && data.available ? (data.count > 0 ? "Continue in the Omarchy terminal window." : "No Omarchy terminal is visible. Recheck, retry, or stop tracking if installation was cancelled.") : "Terminal window status is unavailable. Recheck the default setting."
        })
    }
    Component.onCompleted: refreshHint()

    Column {
        id: pendingColumn
        anchors.fill: parent
        anchors.margins: Style.spacing.md
        spacing: Style.spacing.sm
        Text { text: "Install and set is pending for " + (root.pending ? root.pending.choice : "the selected application"); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; font.bold: true }
        Text { width: parent.width; text: root.terminalHint + " Setting file: selector-owned default file. Recovery: finish the terminal, Recheck, or Stop tracking."; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall; wrapMode: Text.WordWrap }
        Row {
            spacing: Style.spacing.sm
            Ui.Button { text: "Recheck"; bordered: true; focusable: true; onClicked: root.recheck() }
            Ui.Button { text: root.canAbandon ? "Stop tracking" : "Stop tracking unavailable"; bordered: true; focusable: true; enabled: root.canAbandon; onClicked: root.abandon() }
        }
    }
}
