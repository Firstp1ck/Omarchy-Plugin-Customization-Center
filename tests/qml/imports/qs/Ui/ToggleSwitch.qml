import QtQuick
Item {
    property bool checked: false
    property bool busy: false
    signal toggled()
    implicitWidth: 40
    implicitHeight: 24
}
