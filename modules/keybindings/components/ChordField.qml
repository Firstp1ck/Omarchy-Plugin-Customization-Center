import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

ColumnLayout {
    id: root
    property var backendClient: null
    property string moduleId: "keybindings"
    property string value: ""
    property var normalized: null
    property string normalizedText: ""
    property string errorText: ""
    property int requestRevision: 0
    signal chordEdited(string value, var normalized)
    signal captureRequested()

    RowLayout {
        Layout.fillWidth: true
        Ui.TextField {
            id: input
            Layout.fillWidth: true
            text: root.value
            placeholderText: "SUPER + SHIFT + R"
            enabled: !root.parentBusy
            onTextEdited: root.setValueAndNormalize(text)
        }
        Ui.Button { text: "Capture"; focusable: true; onClicked: root.captureRequested() }
    }
    Text { Layout.fillWidth: true; text: root.errorText !== "" ? root.errorText : (root.normalized ? "Canonical: " + root.normalized.display : "Type a global keyboard chord"); color: root.errorText !== "" ? Color.urgent : Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap }

    property bool parentBusy: false
    Timer {
        id: debounce
        interval: 250
        repeat: false
        onTriggered: root.normalizeCurrent()
    }

    function clearNormalization() {
        requestRevision += 1
        normalized = null
        normalizedText = ""
        errorText = ""
    }
    function setValueAndNormalize(text) {
        clearNormalization()
        value = String(text)
        debounce.restart()
    }
    function normalizeCurrent() {
        var requestedText = value
        var revision = requestRevision
        if (!backendClient || typeof backendClient.query !== "function") {
            normalized = null
            normalizedText = ""
            errorText = "Preview unavailable. Recovery: validate the chord from the shared apply review."
            chordEdited(value, null)
            return
        }
        backendClient.query(moduleId, "normalize_chord", { text: requestedText }, function(result) {
            if (revision !== requestRevision || requestedText !== value)
                return
            if (result && result.ok) {
                normalized = result.data
                normalizedText = requestedText
                errorText = ""
            } else {
                normalized = null
                normalizedText = ""
                errorText = result && result.errors && result.errors.length ? result.errors[0].message : "Chord is invalid"
            }
            chordEdited(value, normalized)
        })
    }
    function focusInput() { input.forceActiveFocus() }
}
