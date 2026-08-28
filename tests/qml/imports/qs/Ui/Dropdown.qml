import QtQuick
Item {
    property string value: ""
    property var options: []
    signal changed(string value)
    implicitWidth: 200
    implicitHeight: 30
}
