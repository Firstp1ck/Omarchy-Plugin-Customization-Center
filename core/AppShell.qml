import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

Item {
    id: root

    property var backendClient: null
    property var moduleRegistry: null
    property var draftStore: null
    property var transactionModel: null
    property bool opened: false
    property string backendPath: ""
    property string startupError: ""

    signal requestClose()

    function open(payload) {
        opened = true
        if (transactionModel) transactionModel.open()
        if (moduleRegistry) moduleRegistry.open(payload || ({}))
        forceActiveFocus()
    }

    function close() {
        opened = false
        if (draftStore) draftStore.close()
        if (transactionModel) transactionModel.close()
        if (moduleRegistry) moduleRegistry.close()
    }

    function handlePayload(payload) {
        if (moduleRegistry) moduleRegistry.routePayload(payload || ({}))
    }

    focus: true
    Keys.onEscapePressed: function(event) {
        root.requestClose()
        event.accepted = true
    }

    Rectangle {
        anchors.fill: parent
        color: Color.menu.scrim
    }

    Ui.BorderSurface {
        anchors.centerIn: parent
        width: Math.min(parent.width - Style.spacing.panelPadding * 2, Style.space(1180))
        height: Math.min(parent.height - Style.spacing.panelPadding * 2, Style.space(760))
        color: Color.popups.background
        radius: Style.cornerRadius
        borderSpec: Border.localOrSurfaceSpec("popups", "border", Color.popups.border, Color.popups.border, Style.normalBorderWidth)

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Style.spacing.panelPadding
            spacing: Style.spacing.panelGap

            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: root.moduleRegistry && root.moduleRegistry.selectedModule ? root.moduleRegistry.selectedModule.title : "Customization Center"
                    color: Color.popups.text
                    font.family: Style.font.family
                    font.pixelSize: Style.font.heading
                    font.bold: true
                }
                Ui.Button {
                    text: "Close"
                    iconText: "×"
                    tooltipText: "Close Customization Center"
                    focusable: true
                    onClicked: root.requestClose()
                }
            }

            ErrorBanner {
                Layout.fillWidth: true
                code: {
                    if (root.startupError) return "runtime_unavailable"
                    if (root.transactionModel && root.transactionModel.applyBlocked) return "recovery_required"
                    if (root.moduleRegistry && root.moduleRegistry.errorCode) return root.moduleRegistry.errorCode
                    return applyBar.errorCode
                }
                detail: {
                    if (root.startupError) return root.startupError + "\n" + root.backendPath
                    if (root.moduleRegistry && root.moduleRegistry.errorMessage) return root.moduleRegistry.errorMessage
                    return applyBar.errorMessage
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: Style.spacing.panelGap

                Sidebar {
                    Layout.fillHeight: true
                    modules: root.moduleRegistry ? root.moduleRegistry.modules : []
                    selectedModuleId: root.moduleRegistry ? root.moduleRegistry.selectedModuleId : ""
                    onSelected: function(moduleId) { root.moduleRegistry.select(moduleId, {}) }
                }

                Rectangle {
                    Layout.preferredWidth: Style.spacing.hairline
                    Layout.fillHeight: true
                    color: Color.popups.border
                }

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    Binding {
                        target: root.moduleRegistry
                        property: "parent"
                        value: pageHost
                        when: root.moduleRegistry !== null
                    }
                    Item {
                        id: pageHost
                        anchors.fill: parent
                    }

                    Text {
                        anchors.centerIn: parent
                        visible: root.moduleRegistry && root.moduleRegistry.loading
                        text: "Loading modules…"
                        color: Color.popups.text
                        font.family: Style.font.family
                        font.pixelSize: Style.font.body
                    }
                }
            }

            ChangeList {
                Layout.fillWidth: true
                Layout.preferredHeight: visible ? Style.space(220) : 0
                visible: applyBar.reviewing
                operations: applyBar.planData && applyBar.planData.operations ? applyBar.planData.operations : []
            }

            ApplyBar {
                id: applyBar
                Layout.fillWidth: true
                backendClient: root.backendClient
                draftStore: root.draftStore
                transactionModel: root.transactionModel
                moduleId: root.moduleRegistry ? root.moduleRegistry.selectedModuleId : ""
                status: root.moduleRegistry && root.moduleRegistry.statusByModule ? root.moduleRegistry.statusByModule[moduleId] : null
                onApplied: function(transactionId) {
                    root.moduleRegistry.refreshStatus(moduleId)
                    undoToast.transactionId = transactionId
                    undoToast.opened = transactionId !== ""
                }
            }
        }

        UndoToast {
            id: undoToast
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: Style.spacing.panelPadding
            backendClient: root.backendClient
            onUndoFinished: root.moduleRegistry.refreshStatus(root.moduleRegistry.selectedModuleId)
        }
    }

    Connections {
        target: moduleRegistry
        ignoreUnknownSignals: true
        function onRequestPlan() { applyBar.review() }
        function onRequestApply() { applyBar.requestApply() }
        function onRequestReset() { applyBar.resetDraft() }
    }
}
