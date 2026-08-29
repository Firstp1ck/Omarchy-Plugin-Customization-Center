import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

Flickable {
    id: root
    property string title: "Surface"
    property string sectionName: ""
    property var value: null
    property var defaults: ({})
    property var fields: []
    property bool busy: false
    property string message: ""
    signal sectionRequested(string sectionName, var value)
    clip: true
    contentHeight: content.implicitHeight

    function materialized() { return value === null || value === undefined ? JSON.parse(JSON.stringify(defaults || ({}))) : JSON.parse(JSON.stringify(value)) }
    function setField(key, raw, type) {
        var next = materialized(); var parsed = raw
        if (type === "integer") parsed = Number.parseInt(raw)
        else if (type === "number") parsed = Number(raw)
        else if (type === "nullable-integer") parsed = raw.length ? Number.parseInt(raw) : null
        else if (type === "nullable-string") parsed = raw.length ? raw : null
        next[key] = parsed; sectionRequested(sectionName, next)
    }

    ColumnLayout {
        id: content
        width: root.width
        spacing: Style.spacing.md
        Text { text: root.title; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.title; font.bold: true }
        RowLayout {
            Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: "Inherit generated defaults\nOff writes the complete typed shell." + root.sectionName + ".toml section."; color: Color.foreground; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
            Ui.ToggleSwitch { checked: root.value === null || root.value === undefined; busy: root.busy; Accessible.name: "Inherit " + root.sectionName; onToggled: root.sectionRequested(root.sectionName, checked ? root.materialized() : null) }
        }
        Text { Layout.fillWidth: true; visible: root.message.length > 0; text: root.message; color: Color.muted; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
        Repeater {
            model: root.fields
            delegate: ColumnLayout {
                required property var modelData
                Layout.fillWidth: true
                spacing: Style.spacing.xs
                Text { text: modelData.label || modelData.key; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
                RowLayout {
                    Layout.fillWidth: true
                    visible: modelData.type === "boolean"
                    Text { Layout.fillWidth: true; text: modelData.label || modelData.key; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
                    Ui.ToggleSwitch { checked: !!root.materialized()[modelData.key]; busy: root.busy || root.value === null; Accessible.name: root.sectionName + " " + (modelData.label || modelData.key); onToggled: { var next = root.materialized(); next[modelData.key] = !checked; root.sectionRequested(root.sectionName, next) } }
                }
                Ui.TextField {
                    Layout.fillWidth: true
                    visible: modelData.type !== "boolean"
                    text: { var current = root.materialized()[modelData.key]; return current === null || current === undefined ? "" : String(current) }
                    placeholderText: modelData.placeholder || ""
                    enabled: !root.busy && root.value !== null
                    Accessible.name: (root.sectionName + " " + (modelData.label || modelData.key))
                    onEditingFinished: root.setField(modelData.key, text, modelData.type || "string")
                }
            }
        }
    }
}
