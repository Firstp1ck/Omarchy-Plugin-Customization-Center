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
    property bool handlesPendingHandoffs: true
    property var polledStatus: null
    property var statusPollHandle: null
    property int pollingIntervalMs: 0
    property double pollingNowMsOverride: -1
    property var outcomeOverrides: ({})
    property string pendingCategory: ""

    signal requestPlan()
    signal requestApply()
    signal requestReset()
    signal requestDraftPatch(var patch)
    signal requestNavigate(string moduleId, var payload)

    readonly property var effectiveStatus: polledStatus || status
    readonly property var statusData: effectiveStatus && effectiveStatus.data ? effectiveStatus.data : ({})
    readonly property var fallbackCategories: [
        ({ id: "browser", label: "Browser", summary: "Web links and browser XDG handlers", stateFile: "~/.config/mimeapps.list", state: "loading", choices: [] }),
        ({ id: "terminal", label: "Terminal", summary: "Terminal used by xdg-terminal-exec", stateFile: "~/.config/xdg-terminals.list", state: "loading", choices: [] }),
        ({ id: "editor", label: "Editor", summary: "Editor used by omarchy-launch-editor", stateFile: "~/.local/state/omarchy/defaults/editor", state: "loading", choices: [] }),
        ({ id: "agent", label: "Coding agent", summary: "Coding agent launched by Omarchy", stateFile: "~/.config/omarchy/defaults/agent", state: "loading", choices: [] })
    ]
    readonly property var categories: decoratedCategories(statusData.categories || fallbackCategories)

    function decoratedCategories(source) {
        var result = []
        for (var i = 0; i < source.length; ++i) {
            var item = Object.assign({}, source[i])
            if (Object.prototype.hasOwnProperty.call(outcomeOverrides, item.id))
                item.outcome = outcomeOverrides[item.id]
            result.push(item)
        }
        return result
    }
    function categoryDraft(categoryId) {
        return draft && draft.changes ? draft.changes[categoryId] || null : null
    }
    function patchCategory(categoryId, change) {
        var changesPatch = ({})
        changesPatch[categoryId] = change
        requestDraftPatch(({ schemaVersion: 1, changes: changesPatch }))
    }
    function clearOutcome(categoryId) {
        var next = Object.assign({}, outcomeOverrides)
        next[categoryId] = null
        outcomeOverrides = next
    }
    function cardAt(index) { return cards.itemAt(index) }
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
                var choices = categories[i].choices || []
                for (var j = 0; j < choices.length; ++j) {
                    if (choices[j].id === payload.choice) {
                        clearOutcome(pendingCategory)
                        patchCategory(pendingCategory, ({ choice: payload.choice, install: false }))
                        break
                    }
                }
            }
            break
        }
    }
    function statusFromResult(result) {
        if (!result || !result.ok || !result.data) return null
        return result.data.status || result.data
    }
    function refreshStatus(callback) {
        if (!backendClient) return
        backendClient.status(moduleId, function(result) {
            var next = root.statusFromResult(result)
            if (next) root.polledStatus = next
            root.updatePolling()
            if (callback) callback(result)
        })
    }
    function pendingStartedMs() {
        var earliest = 0
        var list = statusData.categories || []
        for (var i = 0; i < list.length; ++i) {
            var pending = list[i].pending
            if (!pending || !pending.startedAt) continue
            var parsed = Date.parse(pending.startedAt)
            if (!isNaN(parsed) && (earliest === 0 || parsed < earliest)) earliest = parsed
        }
        return earliest
    }
    function pollingIntervalForElapsed(elapsedMs) {
        if (elapsedMs >= 15 * 60 * 1000) return 0
        return elapsedMs < 2 * 60 * 1000 ? 5000 : 20000
    }
    function pollingNowMs() { return pollingNowMsOverride >= 0 ? pollingNowMsOverride : Date.now() }
    function stopStatusPolling() {
        if (backendClient && statusPollHandle) backendClient.stopPolling(statusPollHandle)
        statusPollHandle = null
        pollingIntervalMs = 0
    }
    function updatePolling() {
        if (!backendClient || !visible) {
            stopStatusPolling()
            return
        }
        var pending = statusData.pendingHandoffs || []
        if (pending.length === 0) {
            stopStatusPolling()
            return
        }
        var started = pendingStartedMs()
        var elapsed = started > 0 ? Math.max(0, pollingNowMs() - started) : 0
        var wanted = pollingIntervalForElapsed(elapsed)
        if (wanted === 0) {
            stopStatusPolling()
            return
        }
        if (statusPollHandle && pollingIntervalMs === wanted) return
        stopStatusPolling()
        pollingIntervalMs = wanted
        statusPollHandle = backendClient.pollStatus(moduleId, wanted, function(result) {
            var next = root.statusFromResult(result)
            if (next) root.polledStatus = next
            var listed = root.statusData.pendingHandoffs || []
            for (var i = 0; i < listed.length; ++i)
                backendClient.reconcile(listed[i].id, function() { root.refreshStatus() })
            root.updatePolling()
        })
    }
    function recheck(category) {
        if (category.pending && backendClient)
            backendClient.reconcile(category.pending.transactionId, function() { root.refreshStatus() })
        else
            refreshStatus()
    }
    function abandon(category) {
        if (!category.pending || !backendClient) return
        backendClient.abandon(category.pending.transactionId, function() { root.refreshStatus() })
    }
    function reload(categoryId) {
        clearOutcome(categoryId)
        refreshStatus()
    }
    function retry(category) {
        clearOutcome(category.id)
        var outcome = category.outcome || ({})
        if (outcome.choice)
            patchCategory(category.id, ({ choice: outcome.choice, install: false }))
        else
            refreshStatus()
    }

    onStatusChanged: { polledStatus = null; updatePolling() }
    onBackendClientChanged: { stopStatusPolling(); updatePolling() }
    onVisibleChanged: updatePolling()
    Component.onDestruction: stopStatusPolling()

    Connections {
        target: root.backendClient
        ignoreUnknownSignals: true
        function onRequestStarted(requestId, command, moduleId) {
            if (command === "apply" && moduleId === root.moduleId) root.outcomeOverrides = ({})
        }
        function onRequestFinished(requestId, command, moduleId, result) {
            if (moduleId !== root.moduleId && command !== "reconcile" && command !== "abandon") return
            if (command === "apply" && result && !result.ok && result.errors && result.errors.length) {
                var code = result.errors[0].code
                if (code === "stale_revision" || code === "rollback_failed") {
                    var next = Object.assign({}, root.outcomeOverrides)
                    var changes = root.draft && root.draft.changes ? root.draft.changes : ({})
                    var ids = Object.keys(changes)
                    for (var i = 0; i < ids.length; ++i)
                        next[ids[i]] = ({ state: code === "stale_revision" ? "stale" : "rollback_failed", choice: changes[ids[i]].choice, code: code, reason: result.errors[0].message, paths: (result.data || {}).affectedPaths || [], recoveryCommands: (result.data || {}).recoveryCommands || [] })
                    root.outcomeOverrides = next
                }
            }
            if (["apply", "reconcile", "abandon"].indexOf(command) >= 0) root.refreshStatus()
        }
    }

    Flickable {
        id: scroller
        anchors.fill: parent
        contentWidth: width
        contentHeight: pageColumn.implicitHeight
        clip: true

        Column {
            id: pageColumn
            width: scroller.width
            spacing: (Style.spacing.lg || Style.space(10))

            Text { text: "Default applications"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading; font.bold: true }
            Text { width: parent.width; text: "Set browser, terminal, editor, and coding agent through Omarchy selectors. Missing applications continue in a visible terminal."; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.body; wrapMode: Text.WordWrap }

            Grid {
                id: grid
                width: parent.width
                columns: width >= 1400 ? 2 : 1
                spacing: (Style.spacing.lg || Style.space(10))
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
                        onDraftPatch: function(categoryId, change) { root.clearOutcome(categoryId); root.patchCategory(categoryId, change) }
                        onRequestPlan: root.requestPlan()
                        onRequestApply: root.requestApply()
                        onRequestReset: root.requestReset()
                        onRetry: root.retry(modelData)
                        onRecheck: root.recheck(modelData)
                        onReload: root.reload(modelData.id)
                        onAbandon: root.abandon(modelData)
                    }
                }
            }
        }
    }
}
