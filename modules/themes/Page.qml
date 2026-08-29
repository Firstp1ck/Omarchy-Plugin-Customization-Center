import QtQuick

FocusScope {
    id: root
    property string moduleId: "themes"
    property var status: null
    property var capabilities: ({})
    property var draft: ({})
    property bool busy: false
    property var backendClient: null
    property var pendingPayload: null

    signal requestPlan()
    signal requestApply()
    signal requestReset()
    signal requestDraftPatch(var patch)
    signal requestNavigate(string moduleId, var payload)

    function syncPage() {
        if (!pageLoader.item) return
        pageLoader.item.moduleId = root.moduleId
        pageLoader.item.status = root.status
        pageLoader.item.capabilities = root.capabilities
        pageLoader.item.draft = root.draft
        pageLoader.item.busy = root.busy
        pageLoader.item.backendClient = root.backendClient
    }
    function focusFirst() {
        if (pageLoader.item && typeof pageLoader.item.focusFirst === "function") pageLoader.item.focusFirst()
        else root.forceActiveFocus()
    }
    function handlePayload(payload) {
        pendingPayload = payload || ({})
        if (pageLoader.item && typeof pageLoader.item.handlePayload === "function") pageLoader.item.handlePayload(pendingPayload)
    }

    onModuleIdChanged: syncPage()
    onStatusChanged: syncPage()
    onCapabilitiesChanged: syncPage()
    onDraftChanged: syncPage()
    onBusyChanged: syncPage()
    onBackendClientChanged: syncPage()

    Text {
        anchors.centerIn: parent
        visible: root.status === null
        text: "Loading themes.\nFile: ~/.config/omarchy/themes/<slug>/colors.toml\nSetting: active Omarchy theme\nRecovery: wait, then retry status."
        horizontalAlignment: Text.AlignHCenter
    }

    Loader {
        id: pageLoader
        anchors.fill: parent
        active: root.status !== null
        source: active ? "components/ThemesView.qml" : ""
        onLoaded: {
            root.syncPage()
            if (root.pendingPayload && typeof item.handlePayload === "function") item.handlePayload(root.pendingPayload)
        }
    }

    Connections {
        target: pageLoader.item
        ignoreUnknownSignals: true
        function onRequestPlan() { root.requestPlan() }
        function onRequestApply() { root.requestApply() }
        function onRequestReset() { root.requestReset() }
        function onRequestDraftPatch(patch) { root.requestDraftPatch(patch) }
        function onRequestNavigate(moduleId, payload) { root.requestNavigate(moduleId, payload) }
    }
}
