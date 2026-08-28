import QtQuick
Item {
    property var values: []
    property var options: []
    property string placeholderText: ""
    property string emptyText: ""
    property string noSelectionText: ""
    signal changed(var values)
    implicitWidth: 200
    implicitHeight: 30
}
