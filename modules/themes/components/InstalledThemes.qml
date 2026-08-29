import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

Flickable {
    id: root
    property var themes: []
    property string activeSlug: ""
    property bool busy: false
    property string duplicateSlug: ""
    signal activateRequested(string slug)
    signal openRequested(string slug)
    signal duplicateRequested(string slug, string newSlug)
    signal deleteRequested(string slug)
    clip: true
    contentHeight: content.implicitHeight

    ColumnLayout {
        id: content
        width: root.width
        spacing: Style.spacing.md
        Text { text: "Installed themes"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.title; font.bold: true }
        Text { Layout.fillWidth: true; text: "Open materializes a complete data-only draft. Duplicate saves under the slug entered below. Git and symlink themes remain read-only."; color: Color.muted; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
        Ui.TextField { Layout.fillWidth: true; text: root.duplicateSlug; placeholderText: "duplicate-slug"; Accessible.name: "Duplicate theme slug"; onTextChanged: root.duplicateSlug = text }
        Repeater {
            model: root.themes
            delegate: Ui.BorderSurface {
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: row.implicitHeight + Style.spacing.md * 2
                color: Style.normalFill
                borderSpec: Border.controlSpec(modelData.slug === root.activeSlug ? "selected" : "normal", Color.foreground, Color.accent)
                RowLayout {
                    id: row; anchors.fill: parent; anchors.margins: Style.spacing.md; spacing: Style.spacing.sm
                    ColumnLayout {
                        Layout.fillWidth: true; spacing: Style.spacing.xs
                        Text { text: modelData.slug + (modelData.slug === root.activeSlug ? "  ACTIVE" : ""); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: modelData.slug === root.activeSlug }
                        Text { Layout.fillWidth: true; text: modelData.source + " · " + (modelData.classification || "builtin") + (modelData.unsupportedFiles && modelData.unsupportedFiles.length ? " · extra: " + modelData.unsupportedFiles.join(", ") : ""); color: modelData.hasExecutableConfig ? Color.urgent : Color.muted; elide: Text.ElideRight; font.family: Style.font.family; font.pixelSize: Style.font.caption }
                    }
                    Ui.Button { text: "Activate"; focusable: true; enabled: !root.busy && modelData.slug !== root.activeSlug; Accessible.name: "Activate " + modelData.slug; onClicked: root.activateRequested(modelData.slug) }
                    Ui.Button { text: "Open"; focusable: true; enabled: !root.busy && modelData.classification !== "symlink"; Accessible.name: "Open " + modelData.slug + " in composer"; onClicked: root.openRequested(modelData.slug) }
                    Ui.Button { text: "Duplicate"; focusable: true; enabled: !root.busy && root.duplicateSlug.length > 0 && modelData.classification !== "symlink"; Accessible.name: "Duplicate " + modelData.slug; onClicked: root.duplicateRequested(modelData.slug, root.duplicateSlug) }
                    Ui.Button { text: "Delete"; focusable: true; enabled: !root.busy && modelData.source === "user" && modelData.slug !== root.activeSlug && ["git", "symlink"].indexOf(modelData.classification) < 0; Accessible.name: "Delete " + modelData.slug; onClicked: root.deleteRequested(modelData.slug) }
                }
            }
        }
    }
}
