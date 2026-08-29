import QtQuick
import qs.Commons
import qs.Ui as Ui

Ui.BorderSurface {
    id: root
    property var preview: ({ schemaVersion: 1, rectangles: [], bounds: ({ x: 0, y: 0, width: 0, height: 0 }) })
    property string selectedId: ""
    signal selected(string outputId)
    signal moveRequested(string outputId, int dx, int dy)
    color: Color.background
    borderSpec: Border.controlSpec(activeFocus ? "focus" : "normal", Color.foreground, Color.accent)
    focus: true
    implicitHeight: Style.space(320)
    property int snapStep: 8

    function commitDrag(outputId, dx, dy) {
        var snappedX = Math.round(dx / snapStep) * snapStep
        var snappedY = Math.round(dy / snapStep) * snapStep
        if (snappedX !== 0 || snappedY !== 0) moveRequested(outputId, snappedX, snappedY)
    }

    Keys.onPressed: function(event) {
        if (!root.selectedId) return
        var step = (event.modifiers & Qt.ControlModifier) ? 1 : ((event.modifiers & Qt.ShiftModifier) ? 64 : 8)
        if (event.key === Qt.Key_Left) root.moveRequested(root.selectedId, -step, 0)
        else if (event.key === Qt.Key_Right) root.moveRequested(root.selectedId, step, 0)
        else if (event.key === Qt.Key_Up) root.moveRequested(root.selectedId, 0, -step)
        else if (event.key === Qt.Key_Down) root.moveRequested(root.selectedId, 0, step)
        else return
        event.accepted = true
    }

    Text {
        anchors.centerIn: parent
        visible: !root.preview || !root.preview.rectangles || root.preview.rectangles.length === 0
        text: "No enabled root output. Fix the enabled monitor setting in the profile, then preview again."
        width: parent.width - Style.spacing.panelPadding * 2
        color: Color.muted; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter
        font.family: Style.font.family; font.pixelSize: Style.font.body
    }
    Repeater {
        model: root.preview && root.preview.rectangles ? root.preview.rectangles : []
        delegate: Ui.BorderSurface {
            required property var modelData
            objectName: "canvasOutput-" + modelData.id
            x: Style.spacing.panelPadding + (modelData.x - root.preview.bounds.x) * Math.min(0.12, (root.width - Style.spacing.panelPadding * 2) / Math.max(1, root.preview.bounds.width))
            y: Style.spacing.panelPadding + (modelData.y - root.preview.bounds.y) * Math.min(0.12, (root.width - Style.spacing.panelPadding * 2) / Math.max(1, root.preview.bounds.width))
            width: Math.max(Style.space(72), modelData.width * Math.min(0.12, (root.width - Style.spacing.panelPadding * 2) / Math.max(1, root.preview.bounds.width)))
            height: Math.max(Style.space(44), modelData.height * Math.min(0.12, (root.width - Style.spacing.panelPadding * 2) / Math.max(1, root.preview.bounds.width)))
            color: root.selectedId === modelData.id ? Style.selectionFill : Color.background
            borderSpec: Border.controlSpec(activeFocus ? "focus" : "normal", Color.foreground, Color.accent)
            Text { anchors.centerIn: parent; text: modelData.id; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.caption }
            MouseArea {
                objectName: "dragArea-" + parent.modelData.id
                anchors.fill: parent
                hoverEnabled: true
                preventStealing: true
                cursorShape: Qt.PointingHandCursor
                property real pressX: 0
                property real pressY: 0
                property bool dragSent: false
                onPressed: function(mouse) { pressX = mouse.x; pressY = mouse.y; dragSent = false; root.forceActiveFocus(); root.selected(parent.modelData.id) }
                onPositionChanged: function(mouse) {
                    if (pressed && !dragSent && (mouse.x !== pressX || mouse.y !== pressY)) {
                        dragSent = true
                        root.commitDrag(parent.modelData.id, mouse.x - pressX, mouse.y - pressY)
                    }
                }
                onReleased: function(mouse) { if (!dragSent) root.commitDrag(parent.modelData.id, mouse.x - pressX, mouse.y - pressY) }
            }
        }
    }
}
