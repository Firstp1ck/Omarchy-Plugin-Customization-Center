import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Ui as Ui
import "core"

Item {
    id: root

    property string omarchyPath: ""
    property var shell: null
    property var manifest: null
    property var barWidgetRegistry: null
    property var pluginRegistry: null
    property var service: null
    property bool opened: false
    property var pendingPayload: ({})
    property var appShell: null
    readonly property string backendPath: manifest && manifest.__sourceDir ? manifest.__sourceDir + "/backend/ccctl" : ""

    function open(payloadJson) {
        var payload = ({})
        try {
            payload = JSON.parse(payloadJson || "{}")
            if (!payload || typeof payload !== "object" || Array.isArray(payload))
                payload = ({})
        } catch (error) {
            payload = ({})
        }
        pendingPayload = payload
        if (root.appShell) {
            root.appShell.handlePayload(payload)
            return
        }
        opened = true
    }

    function close() {
        if (root.appShell)
            root.appShell.close()
        draftStore.close()
        transactionModel.close()
        backendClient.stopAllPolling()
        backendClient.acceptingRequests = false
        moduleRegistry.close()
        opened = false
    }

    function requestHostClose() {
        if (shell && typeof shell.hide === "function" && manifest && manifest.id)
            shell.hide(manifest.id)
        else
            close()
    }

    BackendClient {
        id: backendClient
        ccctlPath: root.backendPath
        omarchyPath: root.omarchyPath
        acceptingRequests: root.opened
    }

    DraftStore {
        id: draftStore
        backendClient: backendClient
    }

    TransactionModel {
        id: transactionModel
        backendClient: backendClient
    }

    ModuleRegistry {
        id: moduleRegistry
        backendClient: backendClient
        draftStore: draftStore
        visible: false
    }

    Variants {
        model: Quickshell.screens

        PanelWindow {
            id: overlayWindow
            required property var modelData
            screen: modelData
            visible: root.opened
            anchors { top: true; bottom: true; left: true; right: true }
            color: "transparent"
            exclusionMode: ExclusionMode.Ignore
            WlrLayershell.namespace: "omarchy-customization-center"
            WlrLayershell.layer: WlrLayer.Overlay
            WlrLayershell.keyboardFocus: root.opened ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

            readonly property bool primary: Quickshell.screens.length > 0 && modelData === Quickshell.screens[0]

            Rectangle {
                anchors.fill: parent
                color: Color.menu.scrim
            }

            Loader {
                id: primaryApp
                anchors.fill: parent
                active: root.opened && overlayWindow.primary
                sourceComponent: AppShell {
                    backendClient: backendClient
                    moduleRegistry: moduleRegistry
                    draftStore: draftStore
                    transactionModel: transactionModel
                    backendPath: root.backendPath
                    startupError: moduleRegistry.errorCode !== "" ? "The backend executable is missing, not executable, or failed to start:" : ""
                    onRequestClose: root.requestHostClose()
                }
                onLoaded: {
                    root.appShell = item
                    item.open(root.pendingPayload)
                }
                onActiveChanged: if (!active) root.appShell = null
            }

            Ui.BorderSurface {
                anchors.centerIn: parent
                visible: !overlayWindow.primary
                implicitWidth: secondaryContent.implicitWidth + Style.spacing.panelPadding * 2
                implicitHeight: secondaryContent.implicitHeight + Style.spacing.panelPadding * 2
                color: Color.popups.background
                radius: Style.cornerRadius
                borderSpec: Border.localOrSurfaceSpec("popups", "border", Color.popups.border, Color.popups.border, Style.normalBorderWidth)

                Column {
                    id: secondaryContent
                    anchors.centerIn: parent
                    spacing: Style.spacing.panelGap
                    Text {
                        text: "Customization Center is open on the primary display."
                        color: Color.popups.text
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body
                    }
                    Ui.Button {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "Close"
                        bordered: true
                        focusable: true
                        onClicked: root.requestHostClose()
                    }
                }
            }

            Item {
                anchors.fill: parent
                focus: root.opened && !overlayWindow.primary
                Keys.onEscapePressed: function(event) {
                    root.requestHostClose()
                    event.accepted = true
                }
                Component.onCompleted: if (focus) forceActiveFocus()
            }
        }
    }

    ConfirmationGate {
        backendClient: backendClient
        transactionModel: transactionModel
    }
}
