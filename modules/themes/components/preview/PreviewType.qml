import QtQuick
import QtQuick.Layouts
import qs.Commons
ColumnLayout {
    id: root
    property var tokens: ({})
    readonly property var fontTokens: (tokens.metrics || ({})).font || ({})
    readonly property var spacingTokens: (tokens.metrics || ({})).spacing || ({})
    spacing: spacingTokens.sm || 4
    Repeater {
        model: ["caption", "body-small", "body", "subtitle", "title", "heading", "display", "display-large"]
        delegate: Text { required property string modelData; text: modelData + "  " + (root.fontTokens[modelData] || 12) + "px"; color: root.tokens.palette.foreground; font.family: Style.font.family; font.pixelSize: root.fontTokens[modelData] || 12 }
    }
    Repeater {
        model: ["xxs", "xs", "sm", "md", "lg", "xl", "xxl", "xxxl", "huge", "control-gap", "panel-padding"]
        delegate: RowLayout { required property string modelData; Text { text: modelData; color: root.tokens.palette.muted; font.family: Style.font.family; font.pixelSize: root.fontTokens.caption || 10 } Rectangle { width: Math.max(1, root.spacingTokens[modelData] || 1); height: 4; color: root.tokens.palette.accent } }
    }
}
