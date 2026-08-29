import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

ColumnLayout {
    id: root
    property var mode: ({ version: 1, id: "", name: "", description: "", icon: "", members: ({}), triggers: [] })
    property var memberCapabilities: ({})
    signal modeEdited(var mode)
    spacing: Style.spacing.md
    function copy(value) { return JSON.parse(JSON.stringify(value)) }
    function update(key, value) { var next = copy(mode); next[key] = value; modeEdited(next) }
    function focusFirst() { idField.forceActiveFocus() }
    Ui.TextField { id: idField; objectName: "modeIdField"; Layout.fillWidth: true; placeholderText: "mode-id"; text: root.mode.id || ""; onEditingFinished: root.update("id", text.trim()) }
    Ui.TextField { Layout.fillWidth: true; placeholderText: "Mode name"; text: root.mode.name || ""; onEditingFinished: root.update("name", text.trim()) }
    Ui.TextField { Layout.fillWidth: true; placeholderText: "Description"; text: root.mode.description || ""; onEditingFinished: root.update("description", text) }
    Text { text: "Members"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle }
    Repeater {
        model: ["monitors", "themes", "plugins", "bar", "keybindings", "defaults"]
        ColumnLayout {
            required property string modelData
            Layout.fillWidth: true
            MemberSection {
                Layout.fillWidth: true
                memberId: modelData; title: modelData.charAt(0).toUpperCase() + modelData.slice(1)
                included: root.mode.members && root.mode.members[modelData] !== undefined
                summary: included ? "Inline draft" : "Untouched"
                available: !root.memberCapabilities[modelData] || root.memberCapabilities[modelData].available !== false
                unavailableReason: root.memberCapabilities[modelData] ? root.memberCapabilities[modelData].reason || "" : ""
                onInclusionChanged: function(value) {
                    var next = root.copy(root.mode); if (!next.members) next.members = ({})
                    if (!value) delete next.members[modelData]
                    else if (next.members[modelData] === undefined) next.members[modelData] = ({})
                    root.modeEdited(next)
                }
            }
            Ui.TextField {
                Layout.fillWidth: true
                visible: root.mode.members && root.mode.members[modelData] !== undefined
                placeholderText: "Inline " + modelData + " JSON"
                text: visible ? JSON.stringify(root.mode.members[modelData]) : ""
                onEditingFinished: {
                    try {
                        var next = root.copy(root.mode); next.members[modelData] = JSON.parse(text); root.modeEdited(next)
                    } catch (error) { text = JSON.stringify(root.mode.members[modelData]) }
                }
            }
        }
    }
}
