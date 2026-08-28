import QtQuick
import QtTest
import "../../core"

TestCase {
    id: testCase
    name: "CustomizationCenterCore"
    when: windowShown
    width: 900
    height: 700

    Component { id: draftStoreComponent; DraftStore {} }
    Component { id: backendLogicComponent; BackendLogic {} }
    Component { id: errorBannerComponent; ErrorBanner {} }
    Component { id: confirmDialogComponent; ConfirmDialog { width: 700; height: 500 } }
    Component { id: schemaFormComponent; SchemaForm { width: 700 } }
    Component {
        id: pageLoaderComponent
        Loader { source: "../fixtures/modules/hello/Page.qml" }
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
        compare(typeof page.requestPlan, "function")
        compare(typeof page.requestApply, "function")
        compare(typeof page.requestReset, "function")
        compare(typeof page.draftChanged, "function")
        compare(typeof page.requestNavigate, "function")
        compare(typeof page.focusFirst, "function")
        compare(typeof page.handlePayload, "function")
        page.handlePayload({ source: "test" })
        compare(page.lastPayload.source, "test")
        page.focusFirst()
        compare(page.focusRequested, true)
    }

    function test_backendParsingAndQueueing() {
        var backend = createTemporaryObject(backendLogicComponent, testCase)
        verify(backend !== null)
        var parsed = backend.parseLastJsonLine("diagnostic\n{\"ok\":true,\"data\":{\"value\":3}}\n")
        compare(parsed.ok, true)
        compare(parsed.data.value, 3)
        var malformed = backend.parseLastJsonLine("{\"ok\":true}\ntrailing")
        compare(malformed.ok, false)
        compare(malformed.errors[0].code, "malformed_output")
        verify(backend.queueRead("hello", { id: 1 }))
        verify(!backend.queueRead("hello", { id: 2 }))
        verify(!backend.queueRead("hello", { id: 3 }))
        compare(backend.finishRead("hello").id, 3)
        backend.enqueueMutation({ id: "first" })
        backend.enqueueMutation({ id: "second" })
        compare(backend.takeMutation().id, "first")
        compare(backend.takeMutation().id, "second")
    }

    function test_draftPatchMergeUndoRedo() {
        var store = createTemporaryObject(draftStoreComponent, testCase)
        verify(store !== null)
        store.replace("hello", { nested: { one: 1, two: 2 }, keep: true }, false)
        store.applyPatch("hello", { nested: { two: 9, three: 3 }, keep: null })
        var merged = store.draftFor("hello")
        compare(merged.nested.one, 1)
        compare(merged.nested.two, 9)
        compare(merged.nested.three, 3)
        verify(merged.keep === undefined)
        verify(store.undo("hello"))
        compare(store.draftFor("hello").nested.two, 2)
        compare(store.draftFor("hello").keep, true)
        verify(store.redo("hello"))
        compare(store.draftFor("hello").nested.two, 9)
        verify(store.draftFor("hello").keep === undefined)
    }

    function test_schemaFormRendersEveryNormalizedType() {
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
        compare(form.fieldTypeAt(0), "boolean")
        compare(form.fieldTypeAt(1), "integer")
        compare(form.fieldTypeAt(2), "string")
        compare(form.fieldTypeAt(3), "path")
        compare(form.fieldTypeAt(4), "enum")
        compare(form.fieldTypeAt(5), "multiselect")
    }

    function test_confirmDialogRequiresExactName() {
        var dialog = createTemporaryObject(confirmDialogComponent, testCase, { itemName: "hello", requireTypedName: true })
        verify(dialog !== null)
        dialog.open()
        compare(dialog.confirmationEnabled, false)
        dialog.typedName = "hell"
        compare(dialog.confirmationEnabled, false)
        dialog.typedName = "hello"
        compare(dialog.confirmationEnabled, true)
    }

    function test_errorBannerMapsEverySharedCode() {
        var banner = createTemporaryObject(errorBannerComponent, testCase)
        verify(banner !== null)
        var codes = [
            "stale_revision", "validation_failed", "invalid_draft", "schema_version_unsupported",
            "runtime_unavailable", "capability_missing", "permission_required", "unsupported_config",
            "resource_conflict", "nonreversible_requires_confirmation", "locked", "timeout",
            "malformed_output", "ipc_rejected", "handoff_failed", "verification_failed",
            "rollback_failed", "recovery_required", "transaction_not_found", "transaction_state_invalid",
            "confirmation_invalid", "confirmation_expired", "unknown_module", "unknown_query", "internal_error"
        ]
        for (var i = 0; i < codes.length; ++i) {
            verify(banner.messageFor(codes[i]).length > 0, codes[i])
            verify(Array.isArray(banner.recoveryFor(codes[i])), codes[i])
        }
    }
}
