import QtQuick
import QtQuick.Controls
import qs.Commons

ScrollView {
    id: root
    property string diff: ""
    clip: true

    TextArea {
        text: root.diff
        readOnly: true
        selectByMouse: true
        wrapMode: TextEdit.NoWrap
        color: Color.foreground
        selectionColor: Style.selectionFill
        selectedTextColor: Color.foreground
        font.family: Style.font.family
        font.pixelSize: Style.font.bodySmall
        background: Rectangle { color: Style.normalFill }
    }
}
