import QtQuick
Item {
    property int value: 0
    property int from: 0
    property int to: 100
    property int stepSize: 1
    signal modified(int value)
    implicitWidth: 120
    implicitHeight: 30
}
