import QtQuick
import qs.Commons
import qs.Ui as Ui

Ui.BorderSurface {
    id: root
    property var category: ({})
    property string lastCopiedText: ""
    readonly property var current: category.current || ({})
    readonly property string valueText: current.choice || current.reported || "No selection"
    readonly property string safeUnknownValue: sanitizeUnknown(current.reported || "")
    implicitHeight: valueColumn.implicitHeight + Style.spacing.md * 2
    color: Style.normalFill
    borderSpec: Border.controlSpec("normal", Color.foreground, Color.accent, Color.urgent)

    function sanitizeUnknown(value) {
        var cleaned = String(value).replace(/[\x00-\x1f\x7f]/g, "�")
        return cleaned.length > 120 ? cleaned.slice(0, 120) + "…" : cleaned
    }
    function sourceText() {
        var raw = current.raw || ({})
        if (category.id === "browser") return "xdg-settings reports this desktop id"
        if (category.id === "terminal") return "xdg-terminal-exec resolves this desktop id"
        if (category.id === "editor") return category.stateFile + " contains this value"
        if (category.id === "agent") return category.stateFile + " contains this value"
        return "The selector reports this value"
    }
    function copyUnknownValue() {
        var raw = String(current.reported || "")
        if (!raw) return
        lastCopiedText = raw
        clipboardValue.selectAll()
        clipboardValue.copy()
        clipboardValue.deselect()
    }

    TextEdit {
        id: clipboardValue
        text: String(root.current.reported || "")
        visible: false
    }

    Column {
        id: valueColumn
        anchors.fill: parent
        anchors.margins: Style.spacing.md
        spacing: Style.spacing.xs
        Text {
            text: root.category.state === "unknown" ? "Not an Omarchy choice" : "Current: " + root.valueText
            color: root.category.state === "broken" ? Color.urgent : Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.subtitle
            font.bold: true
        }
        Text {
            objectName: "unknownRawValue"
            width: parent.width
            visible: root.category.state === "unknown"
            text: root.safeUnknownValue
            color: Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WrapAnywhere
        }
        Text {
            objectName: "unknownSource"
            width: parent.width
            visible: root.category.state === "unknown"
            text: root.sourceText() + (root.current.unknownDesktopName ? ". Desktop file name: " + root.current.unknownDesktopName : "")
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }
        Ui.Button {
            objectName: "copyUnknownAction"
            visible: root.category.state === "unknown"
            text: "Copy raw value"
            bordered: true
            focusable: true
            onClicked: root.copyUnknownValue()
        }
        Text {
            width: parent.width
            visible: root.category.state !== "unknown"
            text: "Health: " + (root.category.state || "loading")
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }
    }
}
