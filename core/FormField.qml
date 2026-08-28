import QtQuick
import QtQuick.Layouts
import qs.Commons

ColumnLayout {
    id: root

    property string label: ""
    property string description: ""
    property string stateText: ""
    default property alias fieldContent: fieldSlot.data

    spacing: Style.spacing.labelGap

    RowLayout {
        Layout.fillWidth: true
        Text {
            Layout.fillWidth: true
            text: root.label
            color: Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.body
            font.bold: true
        }
        Text {
            visible: root.stateText !== ""
            text: root.stateText
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.caption
        }
    }

    Item {
        id: fieldSlot
        Layout.fillWidth: true
        implicitHeight: childrenRect.height
    }

    Text {
        Layout.fillWidth: true
        visible: root.description !== ""
        text: root.description
        color: Color.muted
        font.family: Style.font.family
        font.pixelSize: Style.font.caption
        wrapMode: Text.WordWrap
    }
}
