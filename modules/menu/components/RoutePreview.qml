import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

ColumnLayout {
    id: root
    property var backendClient: null
    property var draft: null
    property string moduleId: "menu"
    property string resultText: "Enter a route to preview the setting without opening or running it."
    spacing: Style.spacing.xs

    Text { text: "Route preview"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
    Ui.TextField {
        id: routeField
        Layout.fillWidth: true
        placeholderText: "personal.notes"
        onTextEdited: queryTimer.restart()
    }
    Text { Layout.fillWidth: true; text: root.resultText; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap }
    Timer {
        id: queryTimer
        interval: 250
        repeat: false
        onTriggered: {
            if (!root.backendClient) {
                root.resultText = "Read-only preview is unavailable until BackendClient is connected."
                return
            }
            root.backendClient.query(root.moduleId, "route", ({ input: routeField.text, draft: root.draft }), function(result) {
                var data = result && result.data ? result.data : null
                root.resultText = data ? ("Resolves to " + data.resolved + (data.wouldRunAction ? ". Selecting it would run an action; preview does not run it." : ".")) : "Route preview failed. Fix the route and retry."
            })
        }
    }
}
