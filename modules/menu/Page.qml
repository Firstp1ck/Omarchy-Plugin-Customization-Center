import QtQuick

FocusScope {
    id: root
    property string moduleId: "menu"
    property var status: null
    property var capabilities: ({})
    property var draft: ({})
    property bool busy: false
    property var backendClient: null
    property var pendingPayload: null
    readonly property var contentItem: pageLoader.item
    readonly property bool reviewEnabled: contentItem ? contentItem.reviewEnabled : false
    readonly property bool loadingVisible: root.status === null

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
        if (pageLoader.item && typeof pageLoader.item.focusFirst === "function")
            pageLoader.item.focusFirst()
        else
            root.forceActiveFocus()
    }
    function handlePayload(payload) {
        pendingPayload = payload || ({})
        if (pageLoader.item && typeof pageLoader.item.handlePayload === "function")
            pageLoader.item.handlePayload(pendingPayload)
    }

    onModuleIdChanged: syncPage()
    onStatusChanged: syncPage()
    onCapabilitiesChanged: syncPage()
    onDraftChanged: syncPage()
    onBusyChanged: syncPage()
    onBackendClientChanged: syncPage()

    Text {
        objectName: "menuPageLoading"
        anchors.centerIn: parent
        visible: root.status === null
        text: "Loading ~/.config/omarchy/extensions/omarchy-menu.jsonc for the personal menu setting. Retry by reopening this page."
        wrapMode: Text.WordWrap
    }

    Loader {
        id: pageLoader
        anchors.fill: parent
        active: root.status !== null
        source: active ? "components/MenuPageContent.qml" : ""
        onLoaded: {
            root.syncPage()
            if (root.pendingPayload && typeof item.handlePayload === "function")
                item.handlePayload(root.pendingPayload)
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
