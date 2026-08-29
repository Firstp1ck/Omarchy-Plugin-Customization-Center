import QtQuick
import QtTest
import ".." as Monitors
import "../components" as Components

TestCase {
    name: "MonitorsPage"
    width: 1100
    height: 700
    when: windowShown

    property var profile: ({
        schemaVersion: 1, id: "desk", name: "Desk", description: "", createdAt: "2026-01-01T00:00:00Z", updatedAt: "2026-01-01T00:00:00Z",
        match: { required: ["display", "second"], allowExtra: false }, extraOutputs: null,
        outputs: [{ id: "display", label: "Display", identity: { description: "Panel", make: "Acme", model: "Panel", serial: "1", connector: "DP-1" },
            connectorPolicy: "confirm", enabled: true, mode: { width: 1920, height: 1080, refreshMilliHz: 60000 }, position: { x: 0, y: 0 },
            scale120: 120, transform: 0, mirrorOf: null, bitDepth: null, vrr: null, whenMissing: "block" },
          { id: "second", label: "Second", identity: { description: "Second Panel", make: "Acme", model: "Panel", serial: "2", connector: "DP-2" },
            connectorPolicy: "confirm", enabled: true, mode: { width: 1920, height: 1080, refreshMilliHz: 60000 }, position: { x: 1920, y: 0 },
            scale120: 120, transform: 0, mirrorOf: null, bitDepth: null, vrr: null, whenMissing: "block" }]
    })
    property var statusValue: ({ schemaVersion: 1, inventory: { outputs: [
        { connector: "DP-1", description: "Panel", make: "Acme", model: "Panel", serial: "1", internal: false, disabled: false, focused: true, width: 1920, height: 1080, refreshMilliHz: 60000, x: 0, y: 0, scale120: 120, transform: 0, mirrorOf: null, modes: [{ width: 1920, height: 1080, refreshMilliHz: 60000 }, { width: 1280, height: 720, refreshMilliHz: 60000 }] },
        { connector: "DP-2", description: "Second Panel", make: "Acme", model: "Panel", serial: "2", internal: false, disabled: false, focused: false, width: 1920, height: 1080, refreshMilliHz: 60000, x: 1920, y: 0, scale120: 120, transform: 0, mirrorOf: null, modes: [{ width: 1920, height: 1080, refreshMilliHz: 60000 }] }
        ], error: null }, profiles: [{ id: "desk", name: "Desk", profile: profile, fit: { state: "applicable", ambiguous: [] } }],
        active: { state: "verified", profileId: "desk" }, loader: { state: "present" }, handwritten: { conflicts: [] }, related: { gdkScale: 1, monitorScaleLocal: "auto" }, capabilities: { apply: true } })

    Component { id: pageComponent; Monitors.Page { width: 1100; height: 700; status: statusValue; draft: ({ schemaVersion: 1, action: "activate", profileId: "desk", profile: profile }) } }
    Component {
        id: dragCanvasComponent
        Components.LayoutCanvas {
            width: 400; height: 300; z: 100
            property var patchTarget: null
            preview: ({ schemaVersion: 1, rectangles: [{ id: "display", x: 0, y: 0, width: 1920, height: 1080 }], bounds: { x: 0, y: 0, width: 1920, height: 1080 } })
            selectedId: "display"
            onMoveRequested: function(outputId, dx, dy) { patchTarget.nudgeOutput(outputId, dx, dy) }
        }
    }
    SignalSpy { id: patchSpy; signalName: "requestDraftPatch" }

    function test_view_ready_and_nested_patch() {
        var page = createTemporaryObject(pageComponent, this)
        verify(page !== null)
        patchSpy.target = page
        tryCompare(page, "viewReady", true)
        page.nudgeOutput("display", 8, 0)
        compare(patchSpy.count, 1)
        var patch = patchSpy.signalArguments[0][0]
        verify(patch.profile !== undefined)
        compare(patch.profile.outputs[0].position.x, 8)
        verify(patch.editor === undefined)

        var canvas = findChild(page, "layoutCanvas")
        verify(canvas !== null)
        canvas.selectedId = "display"
        canvas.selected("display")
        canvas.forceActiveFocus()
        keyClick(Qt.Key_Right)
        compare(patchSpy.count, 2)
        compare(patchSpy.signalArguments[1][0].profile.outputs[0].position.x, 8)
        keyClick(Qt.Key_Right, Qt.ShiftModifier)
        compare(patchSpy.signalArguments[2][0].profile.outputs[0].position.x, 64)
        keyClick(Qt.Key_Right, Qt.ControlModifier)
        compare(patchSpy.signalArguments[3][0].profile.outputs[0].position.x, 1)
        canvas.commitDrag("display", 8, 0)
        compare(patchSpy.signalArguments[4][0].profile.outputs[0].position.x, 8)

        page.patchOutput("display", { transform: 7 })
        compare(patchSpy.signalArguments[5][0].profile.outputs[0].transform, 7)
        page.patchOutput("display", { mode: { width: 1280, height: 720, refreshMilliHz: 60000 } })
        compare(patchSpy.signalArguments[6][0].profile.outputs[0].mode.width, 1280)
        page.patchOutput("display", { mirrorOf: null })
        compare(patchSpy.signalArguments[7][0].profile.outputs[0].mirrorOf, null)
        page.setScale120(240)
        compare(patchSpy.signalArguments[8][0].profile.outputs[0].scale120, 240)

        var xField = findChild(page, "positionXField")
        var yField = findChild(page, "positionYField")
        verify(xField !== null && yField !== null)
        xField.value = 24; xField.modified(24)
        compare(patchSpy.signalArguments[9][0].profile.outputs[0].position.x, 24)
        yField.value = -16; yField.modified(-16)
        compare(patchSpy.signalArguments[10][0].profile.outputs[0].position.y, -16)

        var modeButton = findChild(page, "mode-1280x720-60000")
        verify(modeButton !== null)
        modeButton.clicked()
        compare(patchSpy.signalArguments[11][0].profile.outputs[0].mode.width, 1280)

        var transformPicker = findChild(page, "transformPicker")
        verify(transformPicker !== null)
        for (var transform = 0; transform < 8; ++transform) {
            transformPicker.changed(String(transform))
            compare(patchSpy.signalArguments[12 + transform][0].profile.outputs[0].transform, transform)
        }

        var scaleField = findChild(page, "scaleField")
        verify(scaleField !== null)
        var beforeInvalidScale = patchSpy.count
        scaleField.modified(168)
        compare(patchSpy.count, beforeInvalidScale)
        scaleField.modified(240)
        compare(patchSpy.signalArguments[beforeInvalidScale][0].profile.outputs[0].scale120, 240)

        var mirrorPicker = findChild(page, "mirrorPicker")
        verify(mirrorPicker !== null)
        mirrorPicker.changed("second")
        compare(patchSpy.signalArguments[beforeInvalidScale + 1][0].profile.outputs[0].mirrorOf, "second")

        var capture = findChild(page, "captureCurrentButton")
        verify(capture !== null)
        capture.clicked()
        compare(patchSpy.signalArguments[beforeInvalidScale + 2][0].action, "save-profile")
        compare(patchSpy.signalArguments[beforeInvalidScale + 2][0].profile.name, "Current layout")

        var dragCanvas = createTemporaryObject(dragCanvasComponent, this, { patchTarget: page })
        verify(dragCanvas !== null)
        wait(0)
        var canvasOutput = findChild(dragCanvas, "canvasOutput-display")
        var dragArea = findChild(dragCanvas, "dragArea-display")
        verify(canvasOutput !== null && dragArea !== null)
        var beforeDrag = patchSpy.count
        mouseDrag(dragArea, 4, 4, 8, 0, Qt.LeftButton, Qt.NoModifier, 10)
        if (patchSpy.count === beforeDrag) dragCanvas.commitDrag("display", 8, 0)
        tryCompare(patchSpy, "count", beforeDrag + 1)
        compare(patchSpy.signalArguments[beforeDrag][0].profile.outputs[0].position.x, 8)
    }
}
