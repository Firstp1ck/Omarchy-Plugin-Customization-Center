import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Ui as Ui

Item {
    id: root

    property var backendClient: null
    property var transactionModel: null
    readonly property var transaction: transactionModel ? transactionModel.currentTransaction : null
    readonly property bool active: transaction && transaction.state === "awaiting_confirmation"

    function confirmCurrent() {
        if (!active || !backendClient)
            return
        var confirmation = transaction.confirmation || ({})
        backendClient.confirm(transaction.id, confirmation.token || "", function(result) {
            if (result && result.ok && transactionModel)
                transactionModel.refreshCurrent()
        })
    }

    function revertCurrent() {
        if (!active || !backendClient)
            return
        backendClient.rollback(transaction.id, "user", function() {
            if (transactionModel) transactionModel.refreshCurrent()
        })
    }

    Variants {
        model: Quickshell.screens

        PanelWindow {
            id: gateWindow
            required property var modelData
            screen: modelData
            visible: root.active
            anchors { top: true; bottom: true; left: true; right: true }
            color: "transparent"
            exclusionMode: ExclusionMode.Ignore
            WlrLayershell.namespace: "omarchy-customization-center-confirmation"
            WlrLayershell.layer: WlrLayer.Overlay
            WlrLayershell.keyboardFocus: root.active ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

            Rectangle {
                anchors.fill: parent
                color: Color.menu.scrim
            }

            Ui.BorderSurface {
                anchors.centerIn: parent
                width: Math.min(parent.width - Style.spacing.panelPadding * 2, Style.space(520))
                implicitHeight: gateContent.implicitHeight + Style.spacing.panelPadding * 2
                color: Color.popups.background
                radius: Style.cornerRadius
                borderSpec: Border.localOrSurfaceSpec("popups", "border", Color.popups.border, Color.popups.border, Style.normalBorderWidth)

                ColumnLayout {
                    id: gateContent
                    anchors.fill: parent
                    anchors.margins: Style.spacing.panelPadding
                    spacing: Style.spacing.panelGap

                    Text {
                        Layout.fillWidth: true
                        text: "Keep these display settings?"
                        color: Color.popups.text
                        font.family: Style.font.family
                        font.pixelSize: Style.font.heading
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                    }
                    Text {
                        Layout.fillWidth: true
                        property real deadlineMs: root.transaction && root.transaction.confirmation && root.transaction.confirmation.deadline ? Date.parse(root.transaction.confirmation.deadline) : Date.now()
                        property int secondsLeft: Math.max(0, Math.ceil((deadlineMs - Date.now()) / 1000))
                        text: "Reverting in " + secondsLeft + " seconds"
                        color: Color.urgent
                        font.family: Style.font.family
                        font.pixelSize: Style.font.display
                        horizontalAlignment: Text.AlignHCenter
                        Timer {
                            interval: 200
                            repeat: true
                            running: root.active
                            onTriggered: parent.secondsLeft = Math.max(0, Math.ceil((parent.deadlineMs - Date.now()) / 1000))
                        }
                    }
                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter
                        spacing: Style.spacing.md
                        Ui.Button {
                            text: "Revert now"
                            bordered: true
                            focusable: true
                            onClicked: root.revertCurrent()
                        }
                        Ui.Button {
                            text: "Keep settings"
                            bordered: true
                            focusable: true
                            onClicked: root.confirmCurrent()
                        }
                    }
                }
            }
        }
    }
}
