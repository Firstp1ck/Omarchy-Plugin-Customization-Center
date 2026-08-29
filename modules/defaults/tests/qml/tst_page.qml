import QtQuick
import QtTest
import "../../" as Defaults
import "../../components" as Components

TestCase {
    id: testCase
    name: "DefaultsPage"
    when: windowShown
    width: 1000
    height: 800

    Component { id: pageComponent; Defaults.Page { width: 1000; height: 800 } }
    Component { id: currentValueComponent; Components.CurrentValue { width: 600 } }
    Component { id: pickerComponent; Components.ChoicePicker { width: 700 } }
    Component { id: signalSpyComponent; SignalSpy {} }
    Component {
        id: fakeBackendComponent
        QtObject {
            property int pollCount: 0
            property int stopCount: 0
            property int statusCount: 0
            property int reconcileCount: 0
            property int abandonCount: 0
            property int lastInterval: 0
            property var pollCallback: null
            property var statusResult: null
            signal requestStarted(int requestId, string command, string moduleId)
            signal requestFinished(int requestId, string command, string moduleId, var result)
            function pollStatus(moduleId, interval, callback) { pollCount += 1; lastInterval = interval; pollCallback = callback; return ({ id: pollCount }) }
            function stopPolling(handle) { stopCount += 1; pollCallback = null }
            function status(moduleId, callback) { statusCount += 1; callback(statusResult || ({ ok: false })) }
            function reconcile(transactionId, callback) { reconcileCount += 1; if (callback) callback({ ok: true, data: { state: "pending_handoff" } }) }
            function abandon(transactionId, callback) { abandonCount += 1; if (callback) callback({ ok: true, data: { state: "rolled_back" } }) }
            function query(moduleId, name, args, callback) { callback({ ok: true, data: { available: false, count: null } }) }
        }
    }

    function choice(id, state) {
        return { id: id, label: id === "firefox" ? "Firefox" : "Chromium", reported: id,
            state: state || "available", runnable: state !== "missing", commandPath: "/usr/bin/" + id,
            desktopEntryPath: "/usr/share/applications/" + id + ".desktop", package: { name: id, source: "pacman", installed: true },
            installer: { summary: "Install " + id, needsSudo: true, launchesApp: false }, desktopId: id + ".desktop",
            misePackage: null, command: id, aliases: [] }
    }
    function category(id, state, outcome, pending) {
        return { id: id, label: id, summary: "Default " + id, selector: "omarchy-default-" + id,
            stateFile: "/tmp/" + id, state: state || "ready", default: id === "agent" ? null : "chromium",
            current: { choice: "chromium", reported: "chromium", raw: { preference: "chromium.desktop" } },
            checks: [{ id: "selector", ok: true, expected: "chromium", actual: "chromium" }],
            choices: [choice("chromium"), choice("firefox")], pending: pending || null, outcome: outcome || null,
            drifted: false, probeError: state === "probe_error" ? { command: "xdg-terminal-exec", message: "missing", recovery: "install it" } : null }
    }
    function categoriesWith(first) {
        return [first, category("terminal", "ready"), category("editor", "ready"), category("agent", "unset")]
    }
    function pageStatus(first, pendingList) {
        return { revision: "revision", data: { categories: categoriesWith(first), pendingHandoffs: pendingList || [] } }
    }
    function createPage(first, properties) {
        var values = Object.assign({ status: pageStatus(first) }, properties || ({}))
        var page = createTemporaryObject(pageComponent, testCase, values)
        verify(page !== null)
        tryVerify(function() { return page.cardAt(0) !== null })
        return page
    }

    function test_contract_and_four_cards() {
        var page = createPage(category("browser", "ready"))
        compare(page.moduleId, "defaults")
        compare(page.categories.length, 4)
        compare(page.handlesPendingHandoffs, true)
        page.focusFirst()
    }

    function test_all_card_states_and_actions() {
        var cases = [
            ["ready", null, null, null, ["Set", "Details", "Restore default"]],
            ["unset", null, null, null, ["Set", "Details", "Restore default"]],
            ["none_resolvable", null, null, null, ["Set", "Details", "Restore default"]],
            ["broken", null, null, null, ["Repair", "Details", "Restore default"]],
            ["unknown", null, null, null, ["Set", "Details", "Restore default"]],
            ["probe_error", null, null, null, ["Retry", "Details"]],
            ["drafted", null, { schemaVersion: 1, changes: { browser: { choice: "firefox", install: false } } }, null, ["Set", "Details", "Clear", "Restore default"]],
            ["applying", null, null, { busy: true }, []],
            ["pending_handoff", null, null, null, ["Recheck", "Retry", "Stop tracking", "Details"]],
            ["ready", { state: "installed_not_set", choice: "firefox" }, null, null, ["Set", "Details"]],
            ["ready", { state: "verify_failed", choice: "firefox", failedChecks: [] }, null, null, ["Retry", "Recheck", "Details"]],
            ["ready", { state: "rollback_failed", choice: "firefox", paths: ["/tmp/browser"], recoveryCommands: [] }, null, null, ["Recheck", "Details"]],
            ["ready", { state: "stale", choice: "firefox" }, { schemaVersion: 1, changes: { browser: { choice: "firefox", install: false } } }, null, ["Reload", "Details"]]
        ]
        for (var i = 0; i < cases.length; ++i) {
            var state = cases[i][0]
            var outcome = cases[i][1]
            var draft = cases[i][2]
            var props = cases[i][3] || ({})
            if (draft) props.draft = draft
            var pending = state === "pending_handoff" ? { transactionId: "tx-1", choice: "firefox", startedAt: new Date().toISOString() } : null
            var page = createPage(category("browser", state === "pending_handoff" ? "ready" : state, outcome, pending), props)
            var card = page.cardAt(0)
            compare(card.presentationState, outcome ? outcome.state : state, "state case " + i)
            compare(JSON.stringify(card.availableActions), JSON.stringify(cases[i][4]), "actions for " + card.presentationState)
            page.destroy()
        }
    }

    function test_selection_emits_draft_only_and_details_are_keyboard_focusable() {
        var page = createPage(category("browser", "ready"))
        var patchSpy = createTemporaryObject(signalSpyComponent, testCase, { target: page, signalName: "requestDraftPatch" })
        page.cardAt(0).selectChoice(choice("firefox"))
        compare(patchSpy.count, 1)

        var picker = createTemporaryObject(pickerComponent, testCase, { choices: [choice("chromium"), choice("firefox")], selector: "omarchy-default-browser" })
        var pickSpy = createTemporaryObject(signalSpyComponent, testCase, { target: picker, signalName: "choicePicked" })
        var search = findChild(picker, "choiceSearch")
        verify(search !== null)
        search.text = "fire"
        compare(picker.filteredChoices().length, 1)
        var action = findChild(picker, "choiceAction_firefox")
        var details = findChild(picker, "detailsAction_firefox")
        verify(action !== null && details !== null)
        compare(action.focusable, true)
        compare(details.focusable, true)
        action.clicked()
        compare(pickSpy.count, 1)
        details.clicked()
        compare(picker.detailsChoice.id, "firefox")
    }

    function test_unknown_value_is_sanitized_sourced_and_copyable() {
        var raw = "micro\u0001" + "x".repeat(140)
        var view = createTemporaryObject(currentValueComponent, testCase, { category: {
            id: "editor", state: "unknown", stateFile: "/home/test/.local/state/omarchy/defaults/editor",
            current: { choice: null, reported: raw, raw: {} }
        } })
        verify(view !== null)
        verify(view.safeUnknownValue.indexOf("�") >= 0)
        verify(view.safeUnknownValue.length <= 121)
        verify(view.sourceText().indexOf("editor") >= 0)
        view.copyUnknownValue()
        compare(view.lastCopiedText, raw)
        verify(findChild(view, "copyUnknownAction") !== null)
    }

    function test_pending_poll_schedule_switches_and_stops() {
        var backend = createTemporaryObject(fakeBackendComponent, testCase)
        var base = 1000000
        var started = new Date(base).toISOString()
        var pending = { transactionId: "tx-1", choice: "firefox", startedAt: started }
        var first = category("browser", "ready", null, pending)
        backend.statusResult = { ok: true, data: pageStatus(first, [{ id: "tx-1", sentinelExists: false }]) }
        var page = createPage(first, { backendClient: backend, pollingNowMsOverride: base })
        page.polledStatus = pageStatus(first, [{ id: "tx-1", sentinelExists: false }])
        page.pollingNowMsOverride = base
        page.visible = true
        compare(page.statusData.pendingHandoffs.length, 1)
        compare(page.pendingStartedMs(), base)
        compare(page.pollingIntervalForElapsed(0), 5000)
        compare(page.pollingIntervalForElapsed(119999), 5000)
        compare(page.pollingIntervalForElapsed(120000), 20000)
        compare(page.pollingIntervalForElapsed(899999), 20000)
        compare(page.pollingIntervalForElapsed(900000), 0)

        page.statusPollHandle = ({ id: 1 })
        page.pollingIntervalMs = 20000
        page.stopStatusPolling()
        compare(page.pollingIntervalMs, 0)
        compare(backend.stopCount, 1)
    }
}
