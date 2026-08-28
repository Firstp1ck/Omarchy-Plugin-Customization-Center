pragma Singleton
import QtQuick
QtObject {
    property int cornerRadius: 0
    property int normalBorderWidth: 1
    property color normalFill: "transparent"
    property color selectionFill: Color.accent
    property QtObject spacing: QtObject {
        property int hairline: 1; property int xs: 3; property int md: 6; property int huge: 18
        property int controlPaddingX: 10; property int controlPaddingY: 6; property int inputPaddingY: 7
        property int controlHeight: 28; property int rowPaddingX: 12; property int panelGap: 14
        property int panelPadding: 18; property int popupPadding: 14; property int labelGap: 4
        property int numberFieldWidth: 120
    }
    property QtObject font: QtObject {
        property string family: "monospace"; property int caption: 10; property int bodySmall: 11
        property int body: 12; property int subtitle: 13; property int heading: 16; property int display: 24
    }
    function space(value) { return value }
    function normalFillFor(foreground, accent) { return "transparent" }
    function normalBorderFor(foreground, accent) { return foreground }
}
