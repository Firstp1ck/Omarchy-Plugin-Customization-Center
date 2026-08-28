import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

Ui.BorderSurface {
    id: root

    property bool opened: false
    property string transactionId: ""
    property var backendClient: null
    signal undoFinished(var result)

    visible: opened
    color: Color.notifications.background
    radius: Style.cornerRadius
    borderSpec: Border.localOrSurfaceSpec("notifications", "border", Color.notifications.border, Color.notifications.border, Style.normalBorderWidth)
    implicitWidth: row.implicitWidth + Style.spacing.rowPaddingX * 2
    implicitHeight: row.implicitHeight + Style.spacing.rowPaddingX * 2

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: Style.spacing.rowPaddingX
        spacing: Style.spacing.md
        Text {
            text: "Changes applied"
            color: Color.notifications.text
            font.family: Style.font.family
            font.pixelSize: Style.font.body
        }
        Ui.Button {
            text: "Undo"
            focusable: true
            bordered: true
            onClicked: {
                if (!root.backendClient || !root.transactionId) return
                root.backendClient.rollback(root.transactionId, "user", function(result) {
                    root.opened = false
                    root.undoFinished(result)
                })
            }
        }
    }
}
