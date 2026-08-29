import QtQuick

FocusScope {
    id: root
    property string moduleId: "monitors"
    property var status: null
    property var capabilities: ({})
    property var draft: ({})
    property bool busy: false
    property var backendClient: null
    property var lastPayload: null
    readonly property bool viewReady: view.status === Loader.Ready && view.item !== null

    signal requestPlan()
    signal requestApply()
    signal requestReset()
    signal requestDraftPatch(var patch)
    signal requestNavigate(string moduleId, var payload)

    function focusFirst() {
        if (view.item && typeof view.item.focusFirst === "function") view.item.focusFirst()
        else forceActiveFocus()
    }
    function handlePayload(payload) {
        lastPayload = payload
        if (view.item && typeof view.item.handlePayload === "function") view.item.handlePayload(payload)
    }
    function nudgeOutput(outputId, dx, dy) {
        if (viewReady) view.item.nudgeOutput(outputId, dx, dy)
    }
    function patchOutput(outputId, changes) {
        if (viewReady) view.item.patchOutput(outputId, changes)
    }
    function setScale120(value) {
        if (viewReady) view.item.setScale120(value)
    }
    function createFromCurrent() {
        if (viewReady) view.item.createFromCurrent()
    }
    function wire() {
        if (!view.item) return
        view.item.moduleId = Qt.binding(function() { return root.moduleId })
        view.item.status = Qt.binding(function() { return root.status })
        view.item.capabilities = Qt.binding(function() { return root.capabilities })
        view.item.draft = Qt.binding(function() { return root.draft })
        view.item.busy = Qt.binding(function() { return root.busy })
        view.item.backendClient = Qt.binding(function() { return root.backendClient })
        view.item.requestPlan.connect(root.requestPlan)
        view.item.requestApply.connect(root.requestApply)
        view.item.requestReset.connect(root.requestReset)
        view.item.requestDraftPatch.connect(root.requestDraftPatch)
        view.item.requestNavigate.connect(root.requestNavigate)
        if (lastPayload !== null) view.item.handlePayload(lastPayload)
    }

    Loader {
        id: view
        anchors.fill: parent
        source: "components/MonitorsView.qml"
        onLoaded: root.wire()
    }
}
