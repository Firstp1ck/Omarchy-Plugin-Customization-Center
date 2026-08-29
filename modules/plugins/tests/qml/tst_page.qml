import QtQuick
import QtTest
import "../.." as Plugins

TestCase {
    id: testCase
    name: "PluginsPage"
    when: windowShown
    width: 1050; height: 760

    Component { id: pageComponent; Plugins.Page { width: 1020; height: 720 } }

    function fixtureStatus() {
        return ({ revision: "rev:1", data: {
            shell: { available: true, configuredBar: "omarchy.bar", runningBar: "omarchy.bar", barFallback: false },
            rows: [
                { id: "acme.service", name: "Acme Service", description: "A service", kinds: ["service"], firstParty: false,
                  self: false, ownership: "plugins", origin: { class: "user-installed", checkout: "git", sourceDir: "/tmp/acme.service", remote: "https://example.test/acme.git" },
                  state: { enabled: false, canDisable: true }, instances: [], settings: { support: "none", fields: [], problems: [], extension: null }, diagnostics: [], capabilities: ["enable", "update", "remove", "validate"] },
                { id: "acme.widget", name: "Acme Widget", description: "A widget", kinds: ["bar-widget"], firstParty: false,
                  self: false, ownership: "bar", origin: { class: "user-installed", checkout: "directory", sourceDir: "/tmp/acme.widget" },
                  state: { enabled: true, canDisable: true }, instances: [{ section: "right", index: 2, entry: { id: "acme.widget", interval: 5 } }],
                  settings: { support: "schema", fields: [{ key: "interval", type: "integer", label: "Interval", min: 1, max: 60 }], problems: [], extension: null }, diagnostics: [],
                  capabilities: [{ name: "edit-in-bar-editor", navigate: { select: { section: "right", index: 2 } } }] }
            ], pendingHandoffs: [], diagnostics: { warnings: [], undiscovered: [] }
        }})
    }
    function createPage() {
        var page = createTemporaryObject(pageComponent, testCase, { status: fixtureStatus(), draft: { schemaVersion: 1, module: "plugins", baseRevision: "rev:1", changes: [] } })
        verify(page !== null); wait(0); return page
    }
    function test_selection_and_payload_do_not_change_draft() {
        var page = createPage(); var spy = signalSpy.createObject(testCase, { target: page, signalName: "requestDraftPatch" })
        page.handlePayload({ select: "acme.widget", tab: "diagnostics" })
        compare(page.selectedId, "acme.widget"); compare(page.selectedTab, "diagnostics"); compare(spy.count, 0)
    }
    function test_bar_deep_link_exact_payload() {
        var page = createPage(); page.selectRow("acme.widget")
        var spy = signalSpy.createObject(testCase, { target: page, signalName: "requestNavigate" })
        page.deepLink(page.selectedRow)
        compare(spy.count, 1); compare(spy.signalArguments[0][0], "bar")
        compare(spy.signalArguments[0][1].select.section, "right"); compare(spy.signalArguments[0][1].select.index, 2)
    }
    function test_non_bar_toggle_emits_owned_change_only() {
        var page = createPage(); page.selectRow("acme.service")
        var spy = signalSpy.createObject(testCase, { target: page, signalName: "requestDraftPatch" })
        page.setToggle(page.selectedRow)
        compare(spy.count, 1); compare(spy.signalArguments[0][0].changes[0].kind, "enable")
        compare(spy.signalArguments[0][0].changes[0].pluginId, "acme.service")
    }
    function test_settings_form_is_read_only() {
        var page = createPage(); page.selectRow("acme.widget"); page.selectedTab = "settings"; wait(0)
        var form = findChild(page, "readOnlySettingsForm"); verify(form !== null); verify(form.readOnly)
    }
    function test_focus_first_targets_search() {
        var page = createPage(); page.focusFirst(); verify(findChild(page, "pluginSearch").activeFocus)
    }
    Component { id: signalSpy; SignalSpy { } }
}
