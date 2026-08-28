import QtQuick

Item {
    property string moduleId: ""
    property var backendClient: null
    property var status: null
    property var capabilities: ({})
    property var draft: ({})
    property bool busy: false
}
