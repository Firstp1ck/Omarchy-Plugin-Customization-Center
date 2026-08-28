import QtQuick
import QtTest
import "../../core"

TestCase {
    id: testCase
    name: "CustomizationCenterCore"
    when: windowShown
    width: 900
    height: 700
    visible: true

    Component { id: draftStoreComponent; DraftStore {} }
    Component { id: backendLogicComponent; BackendLogic {} }
    Component { id: errorBannerComponent; ErrorBanner {} }
    Component { id: confirmDialogComponent; ConfirmDialog { width: 700; height: 500 } }
    Component { id: schemaFormComponent; SchemaForm { width: 700 } }
    Component { id: transactionModelComponent; TransactionModel {} }
    Component { id: registryComponent; ModuleRegistry { width: 700; height: 500 } }
    Component { id: appShellComponent; AppShell { width: 900; height: 700 } }
    Component { id: confirmationGateLogicComponent; ConfirmationGateLogic {} }
    Component { id: signalSpyComponent; SignalSpy {} }
    Component {
        id: pageLoaderComponent
        Loader { source: "../fixtures/modules/hello/Page.qml" }
    }
    Component {
        id: fakeConfirmationBackendComponent
        QtObject {
            property int confirmCalls: 0
            property string lastTransactionId: ""
            property string lastToken: ""
            function confirm(transactionId, token, callback) {
                confirmCalls += 1
                lastTransactionId = transactionId
                lastToken = token
                callback({ ok: true })
            }
        }
    }
    Component {
        id: fakeRollbackLookupComponent
        QtObject {
            property var results: []
            property int transactionCalls: 0
            function transaction(transactionId, callback) {
                var index = transactionCalls
                transactionCalls += 1
                callback(results[index])
            }
        }
    }
    Component {
        id: fakeBackendComponent
        QtObject {
            property var storedDraft: ({ restored: "from disk" })
            property int saveCount: 0
            property int discardCount: 0
            property int pollCount: 0
            property int stopPollCount: 0
            property bool statusPending: false
            property var pollCallback: null
            property var lastSaved: null
            function draftLoad(moduleId, callback) {
                callback({ ok: true, data: { draft: { draft: storedDraft } } })
            }
            function draftSave(moduleId, draft, callback) {
                saveCount += 1
                lastSaved = draft
                callback({ ok: true, data: {} })
            }
            function draftDiscard(moduleId, callback) {
                discardCount += 1
                if (callback) callback({ ok: true, data: {} })
            }
            function status(moduleId, callback) {
                callback({ ok: true, data: { status: { revision: "revision-1", value: 7 }, pendingHandoffs: statusPending ? [{ id: "handoff-1", sentinelExists: false }] : [] } })
            }
            function pollStatus(moduleId, intervalMs, callback) {
                pollCount += 1
                pollCallback = callback
                return ({ id: pollCount })
            }
            function emitStatusPoll(pending) {
                if (pollCallback)
                    pollCallback({ ok: true, data: { status: { revision: "revision-2", value: 8 }, pendingHandoffs: pending ? [{ id: "handoff-1", sentinelExists: false }] : [] } })
            }
            function stopPolling(handle) { stopPollCount += 1; pollCallback = null }
            function history(callback) { callback({ ok: true, data: { transactions: [] } }) }
            function transaction(transactionId, callback) { callback({ ok: false, data: null }) }
        }
    }

    function pageContractErrors(page) {
        var names = ["requestPlan", "requestApply", "requestReset", "requestDraftPatch", "requestNavigate", "focusFirst", "handlePayload"]
        var errors = []
        for (var i = 0; i < names.length; ++i) {
            if (typeof page[names[i]] !== "function") errors.push("missing " + names[i])
        }
        if (typeof page.draftPatchChanged === "function") errors.push("legacy draftPatchChanged")
        return errors
    }

    function test_pageContract() {
        var loader = createTemporaryObject(pageLoaderComponent, testCase)
        verify(loader !== null)
        tryCompare(loader, "status", Loader.Ready)
        var page = loader.item
        verify(page !== null)
        compare(page.moduleId, "hello")
        verify(page.status === null)
        verify(page.capabilities !== undefined)
        verify(page.draft !== undefined)
        compare(page.busy, false)
        compare(pageContractErrors(page).length, 0)
        page.handlePayload({ source: "test" })
        compare(page.lastPayload.source, "test")
        page.focusFirst()
        compare(page.focusRequested, true)

        var legacy = Qt.createQmlObject(
            "import QtQuick\nItem { property var draft: ({}); signal requestPlan(); signal requestApply(); signal requestReset(); signal draftPatchChanged(var patch); signal requestNavigate(string moduleId, var payload); function focusFirst() {} function handlePayload(payload) {} }",
            testCase,
            "legacyPage")
        var legacyErrors = pageContractErrors(legacy)
        verify(legacyErrors.indexOf("missing requestDraftPatch") >= 0)
        verify(legacyErrors.indexOf("legacy draftPatchChanged") >= 0)
        legacy.destroy()
    }

    function test_selectedPageVisibleAndPersistedDraftRestored() {
        var backend = createTemporaryObject(fakeBackendComponent, testCase)
        var store = createTemporaryObject(draftStoreComponent, testCase, { backendClient: backend })
        var hiddenHost = Qt.createQmlObject("import QtQuick; Item { width: 700; height: 500; visible: true }", testCase, "hiddenHost")
        var registry = createTemporaryObject(registryComponent, hiddenHost, { backendClient: backend, draftStore: store, visible: false })
        registry.modules = [{ id: "hello", title: "Hello", pageUrl: Qt.resolvedUrl("../fixtures/modules/hello/Page.qml"), capabilities: ({}) }]
        verify(registry.select("hello", {}))
        tryVerify(function() { return registry.pageItem !== null })
        wait(0)
        compare(registry.visible, false)
        compare(registry.pageItem.visible, false)

        var appShell = createTemporaryObject(appShellComponent, testCase, {
            backendClient: backend,
            moduleRegistry: registry,
            draftStore: store
        })
        verify(appShell !== null)
        tryCompare(registry, "visible", true)
        verify(registry.parent !== hiddenHost)
        compare(registry.pageItem.visible, true)
        compare(registry.pageItem.draft.restored, "from disk")
        compare(registry.pageItem.status.value, 7)
    }

    function test_activeModulePollsWhileHandoffPending() {
        var backend = createTemporaryObject(fakeBackendComponent, testCase, { statusPending: true })
        var store = createTemporaryObject(draftStoreComponent, testCase, { backendClient: backend })
        var registry = createTemporaryObject(registryComponent, testCase, { backendClient: backend, draftStore: store })
        registry.modules = [{ id: "hello", title: "Hello", pageUrl: Qt.resolvedUrl("../fixtures/modules/hello/Page.qml"), capabilities: ({}) }]
        verify(registry.select("hello", {}))
        compare(backend.pollCount, 1)
        backend.emitStatusPoll(false)
        compare(backend.stopPollCount, 1)
    }

    function test_backendParsingQueueingArgvAndTimeouts() {
        var backend = createTemporaryObject(backendLogicComponent, testCase)
        verify(backend !== null)
        var parsed = backend.parseLastJsonLine("diagnostic\n{\"ok\":true,\"data\":{\"value\":3}}\n")
        compare(parsed.ok, true)
        compare(parsed.data.value, 3)
        var malformed = backend.parseLastJsonLine("{\"ok\":true}\ntrailing garbage")
        compare(malformed.ok, false)
        compare(malformed.errors[0].code, "malformed_output")

        var superseded = null
        verify(backend.queueRead("hello", { id: 1, command: "status", moduleId: "hello" }))
        verify(!backend.queueRead("hello", { id: 2, command: "status", moduleId: "hello", callback: function(result) { superseded = result } }))
        verify(!backend.queueRead("hello", { id: 3, command: "status", moduleId: "hello" }))
        compare(superseded.errors[0].code, "superseded")
        compare(backend.finishRead("hello").id, 3)

        backend.enqueueMutation({ id: "first" })
        backend.enqueueMutation({ id: "second" })
        compare(backend.takeMutation().id, "first")
        compare(backend.takeMutation().id, "second")

        var argv = backend.buildApplyArgv("hello", "rev-2", "digest-3", ["warning-a", "operation-b"])
        compare(JSON.stringify(argv), JSON.stringify([
            "apply", "hello", "--draft", "-", "--expected-revision", "rev-2", "--plan-digest", "digest-3",
            "--confirm", "warning-a", "--confirm", "operation-b"
        ]))
        var plan = { operations: [
            { kind: "WriteFileAtomic", timeoutS: 5, params: {} },
            { kind: "TimedConfirmation", timeoutS: 2, params: { seconds: 30 } }
        ] }
        compare(backend.timeoutFor("apply", plan), 52000)
        compare(backend.timeoutFor("rollback", plan), 52000)

        var retryLookup = createTemporaryObject(fakeRollbackLookupComponent, testCase, { results: [
            { ok: false, errors: [{ code: "superseded", message: "replaced" }] },
            { ok: true, data: { transaction: { plan: plan } } }
        ] })
        var retryDecision = null
        backend.resolveRollbackPlan("tx-retry", retryLookup, function(decision) { retryDecision = decision })
        tryVerify(function() { return retryDecision !== null })
        compare(retryLookup.transactionCalls, 2)
        compare(retryDecision.forceMaximumTimeout, false)
        compare(retryDecision.plan.operations.length, 2)

        var failedLookup = createTemporaryObject(fakeRollbackLookupComponent, testCase, { results: [
            { ok: false, errors: [{ code: "transaction_not_found", message: "missing" }] }
        ] })
        var failedDecision = null
        backend.resolveRollbackPlan("tx-missing", failedLookup, function(decision) { failedDecision = decision })
        verify(failedDecision !== null)
        compare(failedLookup.transactionCalls, 1)
        compare(failedDecision.forceMaximumTimeout, true)
        verify(failedDecision.logLine.indexOf("plan could not be read") >= 0)
        compare(backend.timeoutFor("rollback", failedDecision.plan, failedDecision.forceMaximumTimeout), 15 * 60 * 1000)
    }

    function test_draftDebounceCloseAndHistoryDepth() {
        var backend = createTemporaryObject(fakeBackendComponent, testCase)
        var store = createTemporaryObject(draftStoreComponent, testCase, { backendClient: backend, autosaveDelayMs: 20 })
        store.applyPatch("hello", { value: 1 })
        verify(store.hasPendingSave("hello"))
        tryCompare(backend, "saveCount", 1, 250)
        compare(backend.lastSaved.value, 1)

        store.autosaveDelayMs = 10000
        store.applyPatch("hello", { value: 2 })
        verify(store.hasPendingSave("hello"))
        store.close()
        compare(backend.saveCount, 2)
        compare(backend.lastSaved.value, 2)

        var historyStore = createTemporaryObject(draftStoreComponent, testCase, { autosaveDelayMs: 10000 })
        historyStore.replace("hello", { value: 0 }, false)
        for (var i = 1; i <= 101; ++i)
            historyStore.applyPatch("hello", { value: i })
        compare(historyStore.undoDepth("hello"), 100)
        verify(historyStore.undo("hello"))
        compare(historyStore.draftFor("hello").value, 100)
        compare(historyStore.redoDepth("hello"), 1)
        verify(historyStore.redo("hello"))
        compare(historyStore.draftFor("hello").value, 101)
    }

    function test_schemaFormEditorsAndPatchRoundTrip() {
        var form = createTemporaryObject(schemaFormComponent, testCase, {
            schema: { version: 1, scope: "bar-widget-entry", fields: [
                { key: "enabled", type: "boolean", label: "Enabled", defaultValue: false },
                { key: "count", type: "integer", label: "Count", min: 0, max: 10, step: 1, defaultValue: 2 },
                { key: "name", type: "string", label: "Name", defaultValue: "hello" },
                { key: "path", type: "path", label: "Path", defaultValue: "/tmp" },
                { key: "choice", type: "enum", label: "Choice", options: [{ value: "a", label: "A" }] },
                { key: "many", type: "multiselect", label: "Many", options: [{ value: "a", label: "A" }] }
            ]},
            values: ({})
        })
        verify(form !== null)
        compare(form.renderedFieldCount, 6)
        var types = ["boolean", "integer", "string", "path", "enum", "multiselect"]
        for (var i = 0; i < types.length; ++i) {
            compare(form.fieldTypeAt(i), types[i])
            verify(form.fieldAt(i) !== null)
            verify(form.fieldAt(i).editorItem !== null)
        }
        var booleanEditor = form.fieldAt(0).editorItem
        var integerEditor = form.fieldAt(1).editorItem
        var stringEditor = form.fieldAt(2).editorItem
        var pathEditor = form.fieldAt(3).editorItem
        var enumEditor = form.fieldAt(4).editorItem
        var multiselectEditor = form.fieldAt(5).editorItem
        verify(booleanEditor.checked !== undefined)
        compare(integerEditor.from, 0)
        compare(integerEditor.to, 10)
        compare(integerEditor.value, 2)
        verify(stringEditor.text !== undefined)
        verify(pathEditor.text !== undefined)
        compare(enumEditor.options.length, 1)
        compare(multiselectEditor.options.length, 1)

        var spy = createTemporaryObject(signalSpyComponent, testCase, { target: form, signalName: "requestDraftPatch" })
        integerEditor.value = 8
        integerEditor.modified(8)
        compare(spy.count, 1)
        compare(JSON.stringify(spy.signalArguments[0][0]), JSON.stringify({ count: 8 }))
    }

    function test_confirmationGateRequiresAndPassesClearToken() {
        var backend = createTemporaryObject(fakeConfirmationBackendComponent, testCase)
        var logic = createTemporaryObject(confirmationGateLogicComponent, testCase, { backendClient: backend })
        logic.transaction = { id: "gate-1", state: "awaiting_confirmation", confirmation: { deadline: "2030-01-01T00:00:00Z" } }
        compare(logic.canConfirm, false)
        compare(logic.confirmCurrent(), false)
        compare(backend.confirmCalls, 0)

        logic.transaction = { id: "gate-1", state: "awaiting_confirmation", confirmationToken: "clear-token" }
        compare(logic.canConfirm, true)
        compare(logic.confirmCurrent(), true)
        compare(backend.confirmCalls, 1)
        compare(backend.lastTransactionId, "gate-1")
        compare(backend.lastToken, "clear-token")
    }

    function test_confirmDialogRequiresExactCaseSensitiveName() {
        var dialog = createTemporaryObject(confirmDialogComponent, testCase, { itemName: "hello", requireTypedName: true })
        verify(dialog !== null)
        dialog.open()
        compare(dialog.confirmationEnabled, false)
        dialog.typedName = "hell"
        compare(dialog.confirmationEnabled, false)
        dialog.typedName = "Hello"
        compare(dialog.confirmationEnabled, false)
        dialog.typedName = "hello"
        compare(dialog.confirmationEnabled, true)
    }

    function test_errorBannerMapsEverySharedCodeAndRecovery() {
        var banner = createTemporaryObject(errorBannerComponent, testCase)
        verify(banner !== null)
        var expected = {
            stale_revision: ["Reload", "Compare"], validation_failed: ["Review fields"], invalid_draft: ["Discard draft"],
            schema_version_unsupported: ["Open documentation"], runtime_unavailable: ["Retry", "Start shell"],
            capability_missing: ["Show capability"], permission_required: ["Show path"], unsupported_config: ["Open documentation"],
            resource_conflict: ["Show conflicts"], nonreversible_requires_confirmation: ["Review confirmations"], locked: ["Retry"],
            timeout: ["Retry"], malformed_output: ["Show output"], ipc_rejected: ["Retry"], handoff_failed: ["Retry"],
            verification_failed: ["Show rollback"], rollback_failed: ["Open recovery"], recovery_required: ["Open recovery"],
            transaction_not_found: ["Refresh history"], transaction_state_invalid: ["Refresh"], confirmation_invalid: [],
            confirmation_expired: ["Show rollback"], unknown_module: [], unknown_query: [], internal_error: ["Show logs"]
        }
        var codes = Object.keys(expected)
        for (var i = 0; i < codes.length; ++i) {
            verify(banner.messageFor(codes[i]).length > 0, codes[i])
            compare(JSON.stringify(banner.recoveryFor(codes[i])), JSON.stringify(expected[codes[i]]), codes[i])
        }
        compare(banner.messageFor("superseded"), "")
        compare(banner.recoveryFor("superseded").length, 0)
    }

    function test_transactionModelClearsResolvedPinnedRecovery() {
        var model = createTemporaryObject(transactionModelComponent, testCase)
        var current = model.transactionFromResult({
            ok: true,
            data: {
                transaction: { id: "gate-1", state: "awaiting_confirmation", confirmation: { deadline: "2030-01-01T00:00:00Z" } },
                confirmationToken: "clear-token"
            }
        })
        compare(current.confirmationToken, "clear-token")
        compare(current.confirmation.deadline, "2030-01-01T00:00:00Z")
        model.pinnedRecovery = { id: "failed", state: "rollback_failed" }
        model.history = []
        model._updatePinned()
        compare(model.pinnedRecovery, null)
    }
}
