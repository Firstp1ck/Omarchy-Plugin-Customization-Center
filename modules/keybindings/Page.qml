import QtQuick

Item {
    id: root
    property string moduleId: "keybindings"
    property var status: null
    property var capabilities: ({})
    property var draft: ({})
    property bool busy: false
    property var backendClient: null

    signal requestPlan()
    signal requestApply()
    signal requestReset()
    signal requestDraftPatch(var patch)
    signal requestNavigate(string moduleId, var payload)

    property var pendingPayload: ({})

    function focusFirst() {
        if (view.item && typeof view.item.focusFirst === "function") view.item.focusFirst()
        else forceActiveFocus()
    }
    function handlePayload(payload) {
        pendingPayload = payload || ({})
        if (view.item && typeof view.item.handlePayload === "function") view.item.handlePayload(pendingPayload)
    }
    function updateView() {
        if (!view.item) return
        view.item.moduleId = root.moduleId
        view.item.status = root.status
        view.item.capabilities = root.capabilities
        view.item.draft = root.draft
        view.item.busy = root.busy
        view.item.backendClient = root.backendClient
    }

    Text {
        anchors.centerIn: parent
        visible: root.status === null
        text: "Loading active keybindings from hyprctl.\nFile: ~/.config/hypr/bindings.lua\nSetting: global bindings\nRecovery: wait, then retry status."
        horizontalAlignment: Text.AlignHCenter
    }

    Loader {
        id: view
        anchors.fill: parent
        active: root.status !== null
        source: active ? "components/KeybindingsView.qml" : ""
        onLoaded: {
            root.updateView()
            if (item && typeof item.handlePayload === "function") item.handlePayload(root.pendingPayload)
        }
    }

    onModuleIdChanged: updateView()
    onStatusChanged: updateView()
    onCapabilitiesChanged: updateView()
    onDraftChanged: updateView()
    onBusyChanged: updateView()
    onBackendClientChanged: updateView()

    Connections {
        target: view.item
        ignoreUnknownSignals: true
        function onRequestPlan() { root.requestPlan() }
        function onRequestApply() { root.requestApply() }
        function onRequestReset() { root.requestReset() }
        function onRequestDraftPatch(patch) { root.requestDraftPatch(patch) }
        function onRequestNavigate(moduleId, payload) { root.requestNavigate(moduleId, payload) }
    }
}
