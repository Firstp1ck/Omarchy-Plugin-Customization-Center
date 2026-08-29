import QtQuick
import QtTest
import "../../components"

TestCase {
    name: "KeybindingCapture"
    Component { id: component; ChordCapture {} }
    function test_key_names() {
        var capture = createTemporaryObject(component, this)
        verify(capture !== null)
        compare(capture.keyName(Qt.Key_Tab, ""), "Tab")
        compare(capture.keyName(Qt.Key_Comma, ","), "comma")
        compare(capture.keyName(Qt.Key_A, "a"), "A")
    }
}
