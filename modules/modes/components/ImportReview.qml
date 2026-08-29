import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

ColumnLayout {
    id: root
    property var review: ({})
    property bool commandsReviewed: false
    signal reviewEdited(bool commandsReviewed)
    Text { text: "Imported bundle review"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading }
    Text { text: review.mode ? "Mode " + review.mode.id + " · " + review.mode.collision : ""; color: Color.foreground; font.family: Style.font.family }
    Repeater { model: review.commands || []
        ColumnLayout { required property var modelData; Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: modelData.source + "  " + JSON.stringify(modelData.chord); color: Color.muted; font.family: Style.font.family; wrapMode: Text.WordWrap }
            Text { Layout.fillWidth: true; text: modelData.command; color: Color.foreground; font.family: Style.font.family; wrapMode: Text.WrapAnywhere }
        }
    }
    Ui.ToggleSwitch { visible: (review.commands || []).length > 0; checked: root.commandsReviewed; onToggled: root.reviewEdited(checked) }
    Text { visible: (review.commands || []).length > 0; text: "I reviewed every imported command. Import stores files only; applying remains separate."; color: Color.foreground; font.family: Style.font.family; wrapMode: Text.WordWrap }
}
