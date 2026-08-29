import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

ColumnLayout {
    id: root
    property var backendClient: null
    property string moduleId: "keybindings"
    property string command: ""
    property var entries: []
    signal commandEdited(string command, string catalogId)
    spacing: Style.spacing.sm

    Ui.TextField {
        id: search
        Layout.fillWidth: true
        placeholderText: "Search actions or type a custom command"
        text: root.command
        onTextEdited: {
            root.command = text
            root.commandEdited(text, "")
            queryTimer.restart()
        }
    }
    ListView {
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(contentHeight, Style.space(160))
        model: root.entries
        clip: true
        delegate: Ui.Button {
            required property var modelData
            width: ListView.view.width
            text: String(modelData.title) + "  ·  " + String(modelData.command)
            leftAlign: true
            focusable: true
            onClicked: { root.command = String(modelData.command); root.commandEdited(root.command, String(modelData.id || "")) }
        }
    }
    Text { Layout.fillWidth: true; text: "Custom commands run as your user and are stored as plain text in ~/.config/hypr/bindings.lua. Recovery: remove the managed record from keybindings.json."; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap }
    Timer {
        id: queryTimer
        interval: 250
        onTriggered: if (root.backendClient && typeof root.backendClient.query === "function") root.backendClient.query(root.moduleId, "catalog_search", { text: search.text }, function(result) { root.entries = result && result.ok && result.data ? result.data.entries || [] : [] })
    }
}
