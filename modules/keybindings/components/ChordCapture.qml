import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

Item {
    id: root
    property bool active: false
    property string message: "Press the shortcut"
    signal captured(var chord)
    signal cancelled()
    signal refused(string reason)
    visible: active
    focus: active
    Keys.onPressed: function(event) {
        if (event.isAutoRepeat) { event.accepted = true; return }
        if (event.key === Qt.Key_Escape && event.modifiers === Qt.NoModifier) { root.closeCapture(); event.accepted = true; return }
        if (event.key === Qt.Key_Backspace && event.modifiers === Qt.NoModifier) { root.message = "Cleared. Press another shortcut."; event.accepted = true; return }
        if (root.isModifier(event.key)) { event.accepted = true; return }
        if ((event.modifiers & Qt.GroupSwitchModifier) !== 0) { root.refused("AltGr is not supported; type the chord manually"); root.active = false; event.accepted = true; return }
        var name = root.keyName(event.key, event.text)
        if (name === "") { root.refused("Unrecognized key; type its xkbcommon name manually"); root.active = false; event.accepted = true; return }
        var modifiers = []
        if (event.modifiers & Qt.MetaModifier) modifiers.push("SUPER")
        if (event.modifiers & Qt.ControlModifier) modifiers.push("CTRL")
        if (event.modifiers & Qt.AltModifier) modifiers.push("ALT")
        if (event.modifiers & Qt.ShiftModifier) modifiers.push("SHIFT")
        root.captured({ sourceKeys: modifiers.concat([name]).join(" + "), keyName: name,
                        keycode: event.nativeScanCode, keysym: event.nativeVirtualKey, modifiers: modifiers })
        root.active = false
        timeout.stop()
        event.accepted = true
    }

    Rectangle { anchors.fill: parent; color: Color.background; opacity: 0.96 }
    ColumnLayout {
        anchors.centerIn: parent
        spacing: Style.spacing.lg
        Text { text: root.message; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.title; font.bold: true }
        Text { text: "Existing Hyprland shortcuts may still run. Escape cancels; Backspace clears.\nFile: ~/.config/hypr/bindings.lua. Recovery: use the manual chord field or wev."; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.body; wrapMode: Text.WordWrap; Layout.maximumWidth: Style.space(520) }
        Ui.Button { text: "Cancel capture"; focusable: true; onClicked: root.closeCapture() }
    }
    Timer { id: timeout; interval: 10000; onTriggered: { root.message = "Hyprland kept that shortcut. Type it instead with help from wev."; root.active = false; root.refused(root.message) } }
    function openCapture() { active = true; message = "Press the shortcut"; forceActiveFocus(); timeout.restart() }
    function closeCapture() { active = false; timeout.stop(); cancelled() }
    function isModifier(key) { return key === Qt.Key_Shift || key === Qt.Key_Control || key === Qt.Key_Alt || key === Qt.Key_Meta || key === Qt.Key_AltGr || key === Qt.Key_CapsLock || key === Qt.Key_NumLock }
    function keyName(key, text) {
        if (key >= Qt.Key_A && key <= Qt.Key_Z) return String.fromCharCode(65 + key - Qt.Key_A)
        if (key >= Qt.Key_0 && key <= Qt.Key_9) return String.fromCharCode(48 + key - Qt.Key_0)
        if (key >= Qt.Key_F1 && key <= Qt.Key_F35) return "F" + String(1 + key - Qt.Key_F1)
        var names = ({})
        names[Qt.Key_Space] = "space"; names[Qt.Key_Return] = "Return"; names[Qt.Key_Enter] = "KP_Enter"
        names[Qt.Key_Tab] = "Tab"; names[Qt.Key_Backtab] = "ISO_Left_Tab"; names[Qt.Key_Backspace] = "BackSpace"
        names[Qt.Key_Delete] = "Delete"; names[Qt.Key_Insert] = "Insert"; names[Qt.Key_Home] = "Home"; names[Qt.Key_End] = "End"
        names[Qt.Key_PageUp] = "Prior"; names[Qt.Key_PageDown] = "Next"; names[Qt.Key_Left] = "Left"; names[Qt.Key_Right] = "Right"
        names[Qt.Key_Up] = "Up"; names[Qt.Key_Down] = "Down"; names[Qt.Key_Print] = "Print"
        names[Qt.Key_Comma] = "comma"; names[Qt.Key_Period] = "period"; names[Qt.Key_Slash] = "slash"; names[Qt.Key_Minus] = "minus"; names[Qt.Key_Equal] = "equal"; names[Qt.Key_QuoteLeft] = "grave"
        return names[key] || (text && text.length === 1 ? text : "")
    }
}
