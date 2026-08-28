import QtQuick

Item {
    property string moduleId: "hello"
    property var status: null
    property var capabilities: ({})
    property var draft: ({})
    property bool busy: false

    signal requestPlan()
    signal requestApply()
    signal requestReset()
    signal draftPatchChanged(var patch)
    signal requestNavigate(string moduleId, var payload)

    property var lastPayload: null
    property bool focusRequested: false

    function focusFirst() {
        focusRequested = true
        forceActiveFocus()
    }

    function handlePayload(payload) {
        lastPayload = payload
    }
}
