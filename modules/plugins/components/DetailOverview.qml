import QtQuick
import QtQuick.Layouts
import qs.Commons

ColumnLayout {
    id: root
    property var row: null
    spacing: Style.spacing.md
    Text { text: root.row ? root.row.name : "Select a plugin"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading }
    RowLayout {
        visible: !!root.row
        OriginChip { row: root.row || ({}) }
        StateChip { row: root.row || ({}) }
    }
    TrustBanner { Layout.fillWidth: true; row: root.row }
    Text { Layout.fillWidth: true; visible: !!root.row; wrapMode: Text.WordWrap; text: root.row && root.row.description ? root.row.description : "No description declared."; color: Color.foreground; font.family: Style.font.family }
    Text { Layout.fillWidth: true; visible: !!root.row; wrapMode: Text.WrapAnywhere; text: root.row && root.row.origin ? "Local path: " + (root.row.origin.sourceDir || "Unknown") + "\nCheckout: " + root.row.origin.checkout + (root.row.origin.symlinkTarget ? "\nLinked to " + root.row.origin.symlinkTarget : "") + (root.row.origin.remote ? "\nRemote: " + root.row.origin.remote : "") : ""; color: Color.muted; font.family: Style.font.family }
    Text { Layout.fillWidth: true; visible: !!root.row; text: root.row ? "No persistent load-health record is exposed by omarchy-shell. No error observed is not a health guarantee." : ""; wrapMode: Text.WordWrap; color: Color.muted; font.family: Style.font.family }
}
