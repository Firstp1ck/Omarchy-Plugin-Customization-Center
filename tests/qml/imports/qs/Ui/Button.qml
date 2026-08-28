import QtQuick
Rectangle {
    property string text: ""
    property string iconText: ""
    property string tooltipText: ""
    property bool bordered: false
    property bool focusable: false
    property bool selected: false
    property bool hasCursor: false
    property bool leftAlign: false
    signal clicked()
    implicitWidth: 80
    implicitHeight: 30
}
