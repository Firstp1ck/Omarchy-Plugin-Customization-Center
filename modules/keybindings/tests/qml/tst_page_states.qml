import QtQuick
import QtTest
import "../../components"
import "../.." as Module

TestCase {
    id: testCase
    name: "KeybindingPageStates"
    width: 1200
    height: 800

    QtObject {
        id: backend
        function query(moduleId, name, args, callback) {
            var parts = String(args.text).split("+").map(function(value) { return value.trim() })
            var token = parts[parts.length - 1]
            callback({ ok: true, data: { sourceKeys: String(args.text), display: String(args.text),
                identity: "64:keysym:" + token.toLowerCase(), keyKind: "keysym",
                modifiers: parts.slice(0, parts.length - 1), key: { kind: "keysym", value: token.toLowerCase() }, findings: [] } })
        }
    }
    QtObject {
        id: deferredBackend
        property var requests: []
        function query(moduleId, name, args, callback) { requests = requests.concat([{ text: args.text, callback: callback }]) }
        function reset() { requests = [] }
    }
    Component { id: component; KeybindingsView { width: 1200; height: 800; backendClient: backend } }
    Component { id: chordComponent; ChordField { backendClient: deferredBackend } }
    Component { id: pageComponent; Module.Page { width: 1200; height: 800 } }
    SignalSpy { id: patchSpy; signalName: "requestDraftPatch" }

    function emptyModel() { return { schemaVersion: 1, bindings: [], disabled: [] } }
    function loadedStatus(drift) {
        return { revision: "rev", data: { model: emptyModel(), records: [],
            capabilities: { edit: { available: true, reasons: [] } },
            managedBlock: { state: "present", drift: drift }, warnings: [] } }
    }
    function normalized(source) {
        return { sourceKeys: source, modifiers: ["SUPER"], key: { kind: "keysym", value: "a" } }
    }
    function flags() { return { locked: false, release: false, repeating: false, nonConsuming: false, autoConsuming: false, bypass: false } }
    function defaultRow() {
        return { identity: "64:keysym:space", description: "Omarchy menu", keyToken: "space",
                 catalog: { keys: "SUPER + SPACE", module: "utilities" } }
    }
    function createView(drift) {
        var view = createTemporaryObject(component, testCase, { status: loadedStatus(drift), draft: { model: emptyModel() } })
        verify(view !== null)
        patchSpy.target = view
        patchSpy.clear()
        return view
    }

    function test_loading_state_names_file_setting_and_recovery() {
        var page = createTemporaryObject(pageComponent, testCase)
        verify(page !== null)
        compare(page.status, null)
        var loading = page.children[0]
        verify(String(loading.text).indexOf("bindings.lua") >= 0)
        verify(String(loading.text).indexOf("global bindings") >= 0)
        verify(String(loading.text).indexOf("Recovery") >= 0)
    }
    function test_unavailable_unsupported_empty_and_applying_states() {
        var view = createView(false)
        var banner = findChild(view, "statusBannerText")
        verify(String(banner.text).indexOf("No active bindings") >= 0)
        view.status = { revision: "rev", data: { model: emptyModel(), records: [{ index: 0 }],
            capabilities: { edit: { available: false, reasons: ["unsupported_model"] } },
            managedBlock: { state: "absent", drift: false }, warnings: [] } }
        verify(String(banner.text).indexOf("bindings.lua") >= 0)
        verify(String(banner.text).indexOf("unsupported_model") >= 0)
        verify(String(banner.text).indexOf("Recovery") >= 0)
        view.busy = true
        verify(!findChild(view, "applyButton").enabled)
    }
    function test_add_patch() {
        var view = createView(false)
        view.addBinding(normalized("SUPER + A"), "Alpha", "true", "catalog", flags())
        compare(patchSpy.count, 1)
        var patch = patchSpy.signalArguments[0][0]
        compare(patch.model.bindings.length, 1)
        compare(patch.model.bindings[0].description, "Alpha")
    }
    function test_actual_edit_workflow_changed_then_untouched() {
        var view = createView(false)
        view.addBinding(normalized("SUPER + A"), "Alpha", "true", "", flags())
        var model = patchSpy.signalArguments[0][0].model
        var id = model.bindings[0].id
        view.draft = { model: model }; patchSpy.clear()
        view.startEdit({ managedId: id })
        wait(300)
        var field = findChild(view, "chordField")
        field.setValueAndNormalize("SUPER + B")
        wait(300)
        verify(findChild(view, "saveBindingButton").enabled)
        view.commitEditor()
        var changed = patchSpy.signalArguments[0][0].model
        compare(changed.bindings[0].chord.sourceKeys, "SUPER + B")
        compare(changed.bindings[0].chord.key.value, "b")
        view.draft = { model: changed }; patchSpy.clear()
        view.startEdit({ managedId: id })
        wait(300)
        verify(findChild(view, "saveBindingButton").enabled)
        view.commitEditor()
        compare(patchSpy.signalArguments[0][0].model.bindings[0].chord.sourceKeys, "SUPER + B")
    }
    function test_stale_normalization_response_is_ignored() {
        deferredBackend.reset()
        var field = createTemporaryObject(chordComponent, testCase)
        field.setValueAndNormalize("SUPER + A"); wait(300)
        field.setValueAndNormalize("SUPER + B"); wait(300)
        compare(deferredBackend.requests.length, 2)
        deferredBackend.requests[0].callback({ ok: true, data: normalized("SUPER + A") })
        compare(field.normalized, null)
        deferredBackend.requests[1].callback({ ok: true, data: normalized("SUPER + B") })
        compare(field.normalizedText, "SUPER + B")
        compare(field.normalized.sourceKeys, "SUPER + B")
    }
    function test_edit_patch() {
        var view = createView(false)
        view.addBinding(normalized("SUPER + A"), "Alpha", "true", "", flags())
        var model = patchSpy.signalArguments[0][0].model
        view.draft = { model: model }; patchSpy.clear()
        view.editBinding(model.bindings[0].id, normalized("SUPER + A"), "Edited", "echo edited", "", flags())
        compare(patchSpy.signalArguments[0][0].model.bindings[0].description, "Edited")
    }
    function test_disable_patch() {
        var view = createView(false)
        view.disableDefault(defaultRow(), "disabled", null)
        var disabled = patchSpy.signalArguments[0][0].model.disabled[0]
        compare(disabled.sourceKeys, "SUPER + SPACE")
        compare(disabled.target.module, "utilities")
        compare(disabled.reason, "disabled")
    }
    function test_replace_patch() {
        var view = createView(false)
        view.replaceDefault(defaultRow(), normalized("SUPER + SPACE"), "Replacement", "true", "", flags())
        var model = patchSpy.signalArguments[0][0].model
        compare(model.bindings.length, 1)
        compare(model.disabled[0].reason, "replaced")
        compare(model.disabled[0].replacedBy, model.bindings[0].id)
    }
    function test_drift_gating_and_recovery_patches() {
        var view = component.createObject(null, { status: loadedStatus(false), draft: { model: emptyModel() } })
        verify(view !== null)
        patchSpy.target = view
        patchSpy.clear()
        view.startAdd()
        compare(view.editorOpen, true)
        view.status = loadedStatus(true)
        wait(0)
        compare(view.editorOpen, false)
        compare(findChild(view, "editorForm").visible, false)
        wait(0)
        compare(view.driftMode, true)
        compare(findChild(view, "addBindingButton").visible, false)
        compare(findChild(view, "bindingSearchField").visible, false)
        compare(findChild(view, "bindingFilterControls").visible, false)
        compare(findChild(view, "bindingTableRegion").visible, false)
        compare(findChild(view, "bindingTable").visible, false)
        compare(findChild(view, "normalActions").visible, false)
        compare(findChild(view, "driftActions").visible, true)
        verify(findChild(view, "rewriteDriftButton").visible)
        verify(findChild(view, "rewriteDriftButton").enabled)
        verify(findChild(view, "forgetDriftButton").visible)
        verify(findChild(view, "forgetDriftButton").enabled)
        view.rewriteDrift()
        compare(patchSpy.signalArguments[0][0].recoveryAction, "rewrite")
        patchSpy.clear(); view.forgetManaged()
        compare(patchSpy.signalArguments[0][0].recoveryAction, "forget")
        view.destroy()
    }
}
