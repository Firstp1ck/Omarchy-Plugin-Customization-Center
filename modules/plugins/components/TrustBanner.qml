import QtQuick
import QtQuick.Layouts
import qs.Commons

ColumnLayout {
    id: root
    property var row: null
    visible: !!row && !row.firstParty
    spacing: Style.spacing.xs
    Text {
        Layout.fillWidth: true
        wrapMode: Text.WordWrap
        text: "This plugin runs as unsandboxed code inside omarchy-shell with your user's permissions. Omarchy does not verify or sign it."
        color: Color.urgent
        font.family: Style.font.family
        font.pixelSize: Style.font.body
    }
    Text {
        Layout.fillWidth: true
        visible: !!root.row && root.row.origin && root.row.origin.class === "user-clone"
        wrapMode: Text.WordWrap
        text: root.row ? "While enabled it replaces " + root.row.clonedFrom + ". Disabling or removing it restores " + root.row.clonedFrom + "." : ""
        color: Color.foreground
        font.family: Style.font.family
    }
}
