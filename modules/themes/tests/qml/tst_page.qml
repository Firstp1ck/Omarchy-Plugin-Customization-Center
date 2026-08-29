import QtQuick
import QtTest
import "../../" as Themes
import "../../components" as Components
import "../../components/preview/PreviewResolver.js" as Resolver

TestCase {
    id: testCase
    name: "ThemesComposer"
    when: windowShown
    width: 1400
    height: 900

    Component { id: viewComponent; Components.ThemesView { width: 1400; height: 900 } }
    Component { id: signalSpyComponent; SignalSpy {} }
    Component {
        id: backendComponent
        QtObject {
            property int queryCount: 0
            property int rollbackCount: 0
            signal requestStarted(int requestId, string command, string moduleId)
            signal requestFinished(int requestId, string command, string moduleId, var result)
            function query(moduleId, name, args, callback) {
                queryCount++
                if (name === "import") callback({ ok: true, data: { draft: testCase.draft(args.duplicateSlug || args.slug) } })
                else callback({ ok: true, data: { tokens: Resolver.resolve(args.draft, {}, { effective: !args.portable }), contrast: [] } })
            }
            function rollback(transactionId, reason, callback) { rollbackCount++; callback({ ok: true, data: { state: "committed" } }) }
        }
    }

    function draft(slug) {
        return { schemaVersion: 1, kind: "compose", slug: slug || "ocean-focus", displayName: "Ocean Focus",
            origin: { type: "minimal", slug: "dark", revision: "seed" },
            palette: { mode: "dark", background: "#1a1b26", foreground: "#a9b1d6", accent: "#7aa2f7", red: "#f7768e", yellow: "#e0af68", green: "#9ece6a", cyan: "#449dab", blue: "#7aa2f7", magenta: "#ad8ee6" },
            sections: { bar: null, controls: null, spacing: null, font: null, popups: null, tooltip: null, notifications: null, launcher: null, menu: null, polkit: null, lock: null, "image-picker": null },
            wallpapers: [], preferredWallpaper: null, iconTheme: null, acceptedWarnings: [] }
    }
    function status(openPreview) {
        return { revision: "revision", data: { active: { slug: "old" }, machineOverride: { values: { "font.base-size": 16 } },
            themes: [{ slug: "old", source: "user", classification: "plain", unsupportedFiles: [], hasExecutableConfig: false },
                     { slug: "git", source: "user", classification: "git", unsupportedFiles: ["hyprland.lua"], hasExecutableConfig: true }],
            openPreviewTransaction: openPreview || null }, warnings: [] }
    }

    function test_resolver_sections_metrics_controls_and_masks() {
        var value = draft()
        value.sections.font = { "base-size": 12 }
        var tokens = Resolver.resolve(value, { "font.base-size": 18, "menu.selected-text": "foreground" }, { effective: true })
        compare(tokens.metrics.font.baseSize, 18)
        verify(tokens.metrics.spacing.md > 0)
        compare(tokens.sections.menu["selected-text"], value.palette.foreground)
        compare(tokens.masked.length, 2)
        verify(tokens.controls.focus.border.raw.length > 0)
        compare(Object.keys(tokens.sections).length, 12)
    }

    function test_page_workflows_are_draft_only_and_keyboard_exposed() {
        var backend = createTemporaryObject(backendComponent, testCase)
        var view = createTemporaryObject(viewComponent, testCase, { status: status(null), draft: draft(), backendClient: backend,
            capabilities: { items: [{name:"compose",available:true,reason:""},{name:"tryInShell",available:true,reason:""}] } })
        verify(view !== null)
        var patchSpy = createTemporaryObject(signalSpyComponent, testCase, { target: view, signalName: "requestDraftPatch" })
        var planSpy = createTemporaryObject(signalSpyComponent, testCase, { target: view, signalName: "requestPlan" })
        view.handlePayload({ tab: "diagnostics" })
        compare(view.selectedTab, "diagnostics")
        view.importTheme("old", "old-copy")
        compare(backend.queryCount > 0, true)
        compare(patchSpy.count, 1)
        view.activateTheme("old")
        tryCompare(planSpy, "count", 1)
        view.deleteTheme("old")
        tryCompare(planSpy, "count", 2)
        view.startShellPreview()
        tryCompare(planSpy, "count", 3)
        verify(view.fieldsFor("controls").length >= 22)
        verify(view.fieldsFor("font").length >= 12)
        view.focusFirst()
    }

    function test_open_preview_banner_and_restore_action() {
        var backend = createTemporaryObject(backendComponent, testCase)
        var view = createTemporaryObject(viewComponent, testCase, { status: status({ transactionId: "tx-preview", slug: "ocean-focus" }), draft: draft(), backendClient: backend,
            capabilities: { items: [{name:"compose",available:true,reason:""},{name:"tryInShell",available:false,reason:"open"}] } })
        verify(view.openPreview !== null)
        view.stopShellPreview()
        compare(backend.rollbackCount, 1)
        var planSpy = createTemporaryObject(signalSpyComponent, testCase, { target: view, signalName: "requestPlan" })
        var patchSpy = createTemporaryObject(signalSpyComponent, testCase, { target: view, signalName: "requestDraftPatch" })
        view.updateShellPreview()
        compare(backend.rollbackCount, 2)
        tryCompare(planSpy, "count", 1)
        compare(patchSpy.count, 1)
        view.requestDraftPatch({ palette: { accent: "#ffffff" } })
    }
}
