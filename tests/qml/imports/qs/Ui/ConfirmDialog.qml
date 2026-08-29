import QtQuick
Item {
    property bool opened: false
    property string message: ""
    signal canceled()
    signal confirmed()
    visible: opened
    function handleKey(event) { return false }
}
