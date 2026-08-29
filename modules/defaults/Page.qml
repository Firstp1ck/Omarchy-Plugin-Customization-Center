import QtQuick
import qs.Commons
import qs.Ui as Ui
import "components" as Defaults

FocusScope {
    id: root
    property string moduleId: "defaults"
    property var status: null
    property var capabilities: ({})
    property var draft: ({})
    property bool busy: false
    property var backendClient: null
    property var statusPollHandle: null
    property string pendingCategory: ""

    signal requestPlan()
    signal requestApply()
    signal requestReset()
    signal requestDraftPatch(var patch)
    signal requestNavigate(string moduleId, var payload)

    readonly property var statusData: status && status.data ? status.data : ({})
    readonly property var fallbackCategories: [
        ({ id: "browser", label: "Browser", summary: "Web links and browser XDG handlers", stateFile: "~/.config/mimeapps.list", state: "loading", choices: [] }),
        ({ id: "terminal", label: "Terminal", summary: "Terminal used by xdg-terminal-exec", stateFile: "~/.config/xdg-terminals.list", state: "loading", choices: [] }),
        ({ id: "editor", label: "Editor", summary: "Editor used by omarchy-launch-editor", stateFile: "~/.local/state/omarchy/defaults/editor", state: "loading", choices: [] }),
        ({ id: "agent", label: "Coding agent", summary: "Coding agent launched by Omarchy", stateFile: "~/.config/omarchy/defaults/agent", state: "loading", choices: [] })
    ]
    readonly property var categories: statusData.categories || fallbackCategories

    function categoryDraft(categoryId) {
        return draft && draft.changes ? draft.changes[categoryId] || null : null
    }
    function patchCategory(categoryId, change) {
        var changesPatch = ({})
        changesPatch[categoryId] = change
        requestDraftPatch(({ schemaVersion: 1, changes: changesPatch }))
    }
    function focusFirst() {
        var first = cards.itemAt(0)
        if (first) first.focusFirst()
        else root.forceActiveFocus()
    }
    function handlePayload(payload) {
        if (!payload || (payload.module && payload.module !== moduleId)) return
        pendingCategory = payload.category || ""
        for (var i = 0; i < categories.length; ++i) {
            if (categories[i].id !== pendingCategory) continue
            var card = cards.itemAt(i)
            if (card) card.focusFirst()
            if (payload.choice) {
                var valid = false
                var choices = categories[i].choices || []
                for (var j = 0; j < choices.length; ++j) if (choices[j].id === payload.choice) valid = true
                if (valid) patchCategory(pendingCategory, ({ choice: payload.choice, install: false }))
            }
            break
        }
    }
    function stopStatusPolling() {
        if (backendClient && statusPollHandle) backendClient.stopPolling(statusPollHandle)
        statusPollHandle = null
    }
    function updatePolling() {
        if (!backendClient) return
        var pending = statusData.pendingHandoffs || []
        if (pending.length > 0 && !statusPollHandle) {
            statusPollHandle = backendClient.pollStatus(moduleId, 5000, function() {
                var listed = root.statusData.pendingHandoffs || []
                for (var i = 0; i < listed.length; ++i) backendClient.reconcile(listed[i].id)
            })
        } else if (pending.length === 0) {
            stopStatusPolling()
        }
    }

    onStatusChanged: updatePolling()
    onBackendClientChanged: { stopStatusPolling(); updatePolling() }
    Component.onDestruction: stopStatusPolling()

    Flickable {
        id: scroller
        anchors.fill: parent
        contentWidth: width
        contentHeight: pageColumn.implicitHeight
        clip: true

        Column {
            id: pageColumn
            width: scroller.width
            spacing: Style.spacing.lg

            Text { text: "Default applications"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading; font.bold: true }
            Text { width: parent.width; text: "Set browser, terminal, editor, and coding agent through Omarchy selectors. Missing applications continue in a visible terminal."; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.body; wrapMode: Text.WordWrap }

            Grid {
                id: grid
                width: parent.width
                columns: width >= 1400 ? 2 : 1
                spacing: Style.spacing.lg
                Repeater {
                    id: cards
                    model: root.categories
                    delegate: Defaults.CategoryCard {
                        required property var modelData
                        width: grid.columns === 2 ? (grid.width - grid.spacing) / 2 : grid.width
                        category: modelData
                        categoryDraft: root.categoryDraft(modelData.id)
                        backendClient: root.backendClient
                        busy: root.busy
                        onDraftPatch: function(categoryId, change) { root.patchCategory(categoryId, change) }
                        onRequestPlan: root.requestPlan()
                        onRequestApply: root.requestApply()
                        onRequestReset: root.requestReset()
                    }
                }
            }
        }
    }
}
