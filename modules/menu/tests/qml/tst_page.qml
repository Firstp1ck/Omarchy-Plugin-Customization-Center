import QtQuick
import QtTest
import "../.." as Menu

TestCase {
    id: testCase
    name: "MenuPageStates"
    width: 1000
    height: 700
    when: windowShown

    property var readyStatus: ({
        revision: "menu1:test:absent",
        data: {
            documentState: "ok",
            overrideSemantics: "full-shadow",
            user: { path: "/tmp/home/.config/omarchy/extensions/omarchy-menu.jsonc" },
            document: { shape: "direct", entries: [], wrapperSiblings: [] },
            effective: {
                order: ["root", "old"],
                rows: {
                    root: { id: "root", origin: "injected-root", depth: 0, route: "root", kind: "menu", parent: "", children: ["old"], structurallyHidden: false, fields: { label: "Go", icon: "", iconFont: "", action: "", target: "", provider: "", aliases: [] } },
                    old: { id: "old", origin: "custom", depth: 0, route: "old", kind: "action", parent: "root", children: [], structurallyHidden: false, fields: { label: "Old", icon: "", iconFont: "", action: "true", target: "", provider: "", aliases: [] } }
                }
            }
        }
    })
    property var shellUp: ({ items: [{ name: "shell", available: true, reason: "" }] })
    property var shellDown: ({ items: [{ name: "shell", available: false, reason: "not running" }] })

    function statusFor(state) {
        return {
            revision: "menu1:test:" + state,
            data: Object.assign({}, readyStatus.data, {
                documentState: state,
                document: state === "malformed" ? null : { shape: "direct", entries: [], wrapperSiblings: [] }
            })
        }
    }

    QtObject {
        id: fakeBackend
        function query(moduleId, name, args, callback) {
            var rows = Object.assign({}, testCase.readyStatus.data.effective.rows)
            var order = testCase.readyStatus.data.effective.order.slice()
            var entries = args.draft && args.draft.entries ? args.draft.entries : []
            for (var i = 0; i < entries.length; ++i) {
                var entry = entries[i]
                if (entry.deleted) {
                    if (rows[entry.id]) rows[entry.id] = Object.assign({}, rows[entry.id], { draftState: "deleted" })
                } else {
                    if (order.indexOf(entry.id) < 0) order.push(entry.id)
                    rows[entry.id] = { id: entry.id, origin: "custom", draftState: "draft", depth: 0,
                        route: entry.id, kind: entry.kind === "command" ? "action" : "menu", parent: "root",
                        children: [], structurallyHidden: false,
                        fields: Object.assign({ label: entry.id, icon: "", iconFont: "", action: "", target: "", provider: "", aliases: [] }, entry.fields || ({})) }
                }
            }
            callback({ data: { schemaVersion: 1, effective: { order: order, rows: rows } } })
        }
    }

    Component {
        id: pageComponent
        Menu.Page {
            width: 1000
            height: 700
            status: testCase.readyStatus
            capabilities: testCase.shellUp
            backendClient: fakeBackend
        }
    }

    function newPage(properties) {
        var page = createTemporaryObject(pageComponent, testCase, properties || ({}))
        verify(page !== null)
        tryVerify(function() { return page.contentItem !== null }, 1000)
        compare(page.contentItem.objectName, "menuPageContent")
        return page
    }

    function test_content_loads_with_stub_imports() {
        newPage()
    }

    function test_loading_state_before_status_arrives() {
        var page = createTemporaryObject(pageComponent, testCase, { status: null })
        verify(page !== null)
        compare(page.contentItem, null)
        compare(page.loadingVisible, true)
    }

    function test_empty_and_malformed_recovery_states() {
        var emptyPage = newPage({ status: statusFor("empty") })
        compare(emptyPage.contentItem.documentState, "empty")
        compare(emptyPage.contentItem.recoveryState, false)
        compare(emptyPage.contentItem.editorVisible, true)

        var recoveryPage = newPage({ status: statusFor("malformed") })
        compare(recoveryPage.contentItem.recoveryState, true)
        compare(recoveryPage.contentItem.recoveryVisible, true)
        compare(recoveryPage.contentItem.editorVisible, false)
    }

    function test_duplicate_keys_continue_opens_editor_and_review() {
        var duplicateStatus = statusFor("duplicate-keys")
        var page = newPage({ status: duplicateStatus })
        patchSpy.clear()
        patchSpy.target = page
        compare(page.contentItem.recoveryState, true)
        page.contentItem.beginRecovery()
        compare(patchSpy.count, 1)
        compare(page.contentItem.recoveryState, false)
        compare(page.contentItem.reviewEnabled, true)
        compare(page.contentItem.editorVisible, true)
    }

    function test_shell_unavailable_disables_review_and_apply() {
        var page = newPage({ capabilities: shellDown })
        tryCompare(page.contentItem, "reviewEnabled", false)
        var review = findChild(page.contentItem, "menuReviewButton")
        var apply = findChild(page.contentItem, "menuApplyButton")
        verify(review !== null && apply !== null)
        compare(review.enabled, false)
        compare(apply.enabled, false)

        var missing = newPage({ capabilities: ({}) })
        compare(missing.contentItem.shellUnavailable, true)
        compare(missing.contentItem.shellUnavailableReason, "Shell capability was not reported")
        var unrelated = newPage({ capabilities: ({ items: [{ name: "bash", available: true, reason: "" }] }) })
        compare(unrelated.contentItem.shellUnavailable, true)
        compare(unrelated.contentItem.reviewEnabled, false)
    }

    function test_projection_shows_added_and_marks_deleted() {
        var page = newPage()
        page.draft = { schemaVersion: 1, module: "menu", baseRevision: "menu1:test:absent", semantics: "full-shadow",
            shape: "direct", bom: false, wrapperSiblings: [], recovery: null,
            entries: [
                { draftId: "old", id: "old", originalId: "old", origin: "custom", kind: "command", fields: { label: "Old", action: "true" }, passthrough: {}, raw: null, deleted: true },
                { draftId: "new", id: "new", originalId: null, origin: "custom", kind: "submenu", fields: { label: "New" }, passthrough: {}, raw: null, deleted: false }
            ] }
        tryCompare(page.contentItem.effective.rows.old, "draftState", "deleted")
        compare(page.contentItem.effective.rows.new.draftState, "draft")
        verify(page.contentItem.effective.order.indexOf("new") >= 0)
    }

    function test_delete_waits_for_confirmation() {
        var page = newPage()
        page.draft = { schemaVersion: 1, module: "menu", baseRevision: "menu1:test:absent", semantics: "full-shadow",
            shape: "direct", bom: false, wrapperSiblings: [], recovery: null,
            entries: [{ draftId: "old", id: "old", originalId: "old", origin: "custom", kind: "command", fields: { label: "Old", action: "true" }, passthrough: {}, raw: null, deleted: false }] }
        page.contentItem.selectedId = "old"
        patchSpy.clear()
        patchSpy.target = page
        page.contentItem.requestDeleteSelected()
        compare(patchSpy.count, 0)
        compare(page.contentItem.deletePromptVisible, true)
        compare(page.contentItem.deleteDialog.opened, false)
        var input = findChild(page.contentItem, "menuDeleteEntryId")
        var continueButton = findChild(page.contentItem, "menuDeleteContinue")
        verify(input !== null && continueButton !== null)
        input.text = "old"
        tryCompare(continueButton, "enabled", true)
        continueButton.clicked()
        compare(page.contentItem.deleteDialog.opened, true)
        page.contentItem.deleteDialog.confirmed()
        compare(patchSpy.count, 1)
        verify(patchSpy.signalArguments[0][0].entries[0].deleted)
    }

    SignalSpy { id: patchSpy; signalName: "requestDraftPatch" }
}
