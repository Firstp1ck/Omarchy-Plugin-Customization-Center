import QtQuick
import QtTest
import "../.." as Bar

TestCase {
    id: testCase
    name: "BarPage"
    when: windowShown
    width: 1000; height: 760

    Component { id: pageComponent; Bar.Page { width: 980; height: 720 } }

    function fixtureStatus() {
        return ({ revision: "rev:1", data: {
            shell: { available: true, configuredBarId: "omarchy.bar", activeBarId: "omarchy.bar", fallback: false, scanning: false },
            file: { exists: true, parses: true, version1: true },
            bar: { id: null, position: "top", transparent: false, centerAnchor: "omarchy.clock", extra: {}, layout: {
                left: [{ key: "b:left:0", origin: { section: "left", index: 0 }, id: "omarchy.menu", settings: {}, form: "object" }],
                center: [{ key: "b:center:0", origin: { section: "center", index: 0 }, id: "omarchy.clock", settings: {}, form: "object" }], right: [] } },
            catalog: [{ id: "omarchy.menu", displayName: "Menu", presence: "shell", allowMultiple: false, defaultSection: "left", defaults: {}, schema: { ok: true, fields: [] } },
                      { id: "omarchy.clock", displayName: "Clock", presence: "shell", allowMultiple: false, defaultSection: "center", defaults: {}, schema: { ok: true, fields: [] } }],
            barOptions: [{ id: "omarchy.bar", name: "Built-in", available: true }, { id: "local.neon", name: "Neon", available: true }]
        }})
    }
    function fixtureDraft() {
        return ({ schemaVersion: 1, module: "bar", baseRevision: "rev:1", bar: {
            id: null, position: "top", transparent: false, centerAnchor: "omarchy.clock", extra: {}, layout: {
                left: [{ key: "d:menu", origin: { section: "left", index: 0 }, id: "omarchy.menu", settings: {}, form: "object" }],
                center: [{ key: "d:clock", origin: { section: "center", index: 0 }, id: "omarchy.clock", settings: {}, form: "object" }], right: [] }
        }})
    }
    function createPage() {
        var page = createTemporaryObject(pageComponent, testCase, { status: fixtureStatus(), draft: fixtureDraft() })
        verify(page !== null)
        wait(0)
        return page
    }
    function test_selection_payload_has_no_mutation() {
        var page = createPage(); var spy = signalSpy.createObject(testCase, { target: page, signalName: "requestDraftPatch" })
        page.handlePayload({ select: { section: "center", index: 0 } })
        compare(page.selectedKey, "d:clock"); compare(spy.count, 0)
    }
    function test_select_bar_payload_and_position_control_patch() {
        var page = createPage(); var spy = signalSpy.createObject(testCase, { target: page, signalName: "requestDraftPatch" })
        page.handlePayload({ selectBar: "local.neon" }); compare(spy.count, 1)
        var position = findChild(page, "positionSelector"); verify(position !== null)
        position.changed("left"); compare(spy.count, 2); compare(spy.signalArguments[1][0].bar.position, "left")
    }
    function test_unknown_bar_payload_does_not_mutate() {
        var page = createPage(); var spy = signalSpy.createObject(testCase, { target: page, signalName: "requestDraftPatch" })
        page.handlePayload({ selectBar: "missing.bar" }); compare(spy.count, 0); verify(page.toastText.length > 0)
    }
    Component { id: signalSpy; SignalSpy { } }
}
