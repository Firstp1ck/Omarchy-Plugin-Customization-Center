import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

FocusScope {
    id: root
    property string moduleId: "themes"
    property var status: null
    property var capabilities: ({})
    property var draft: ({})
    property bool busy: false
    property var backendClient: null

    signal requestPlan()
    signal requestApply()
    signal requestReset()
    signal requestDraftPatch(var patch)
    signal requestNavigate(string moduleId, var payload)

    property string selectedTab: "palette"
    property var previewPayload: null
    property string previewError: ""
    property bool previewLoading: false
    property var pendingPayload: null

    function capability(name) {
        var items = capabilities && capabilities.items ? capabilities.items : []
        for (var index = 0; index < items.length; ++index)
            if (items[index].name === name) return items[index]
        return ({ available: true, reason: "" })
    }
    function focusFirst() { paletteTab.forceActiveFocus() }
    function handlePayload(payload) {
        pendingPayload = payload || ({})
        if (payload && typeof payload.tab === "string" && ["palette", "surfaces", "type", "bar", "wallpapers", "diagnostics", "themes"].indexOf(payload.tab) >= 0)
            selectedTab = payload.tab
        if (payload && typeof payload.slug === "string") {
            selectedTab = "themes"
            requestDraftPatch({ slug: payload.slug })
        }
        if (payload && typeof payload.activate === "string") {
            selectedTab = "themes"
            requestDraftPatch({ schemaVersion: 1, kind: "activate", slug: payload.activate, preferredWallpaper: null })
        }
    }
    function requestPreview() {
        if (!backendClient || !draft || draft.kind !== "compose") return
        previewLoading = true
        previewError = ""
        backendClient.query(moduleId, "preview", { draft: draft, portable: true }, function(result) {
            previewLoading = false
            if (result && result.ok && result.data) previewPayload = result.data
            else previewError = result && result.error ? String(result.error.message || result.error.code) : "Preview query failed"
        })
    }

    onDraftChanged: previewTimer.restart()
    onStatusChanged: previewTimer.restart()

    Timer { id: previewTimer; interval: 120; repeat: false; onTriggered: root.requestPreview() }

    readonly property bool composeUnavailable: !capability("compose").available
    readonly property bool unsupported: status && status.warnings && status.warnings.length > 0
    readonly property bool recovering: status && status.data && status.data.openPreviewTransaction !== null
    readonly property bool emptyState: status && status.data && status.data.themes && status.data.themes.length === 0

    Text {
        anchors.centerIn: parent
        visible: root.status === null
        text: "Loading themes.\nFile: ~/.config/omarchy/themes/<slug>/colors.toml\nSetting: active Omarchy theme\nRecovery: wait, then retry status."
        color: Color.foreground
        font.family: Style.font.family
        font.pixelSize: Style.font.body
        horizontalAlignment: Text.AlignHCenter
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Style.spacing.panelPadding
        spacing: Style.spacing.md
        visible: root.status !== null

        Text {
            Layout.fillWidth: true
            text: "Theme composer"
            color: Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.heading
            font.bold: true
        }

        Ui.BorderSurface {
            Layout.fillWidth: true
            visible: root.composeUnavailable
            color: Color.popups.background
            borderSpec: Border.surfaceSpec("notifications", "border")
            implicitHeight: unavailableText.implicitHeight + Style.spacing.xl * 2
            Text {
                id: unavailableText
                anchors.fill: parent; anchors.margins: Style.spacing.xl
                text: "Theme composition unavailable: " + root.capability("compose").reason + "\nFile: $OMARCHY_PATH/default/themed/shell.toml.tpl\nSetting: palette and surface composition\nRecovery: restore the Omarchy template and retry."
                color: Color.urgent; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.body
            }
        }

        Text {
            Layout.fillWidth: true
            visible: root.unsupported
            text: "Unsupported theme configuration detected. File: shell.toml.tpl or a user theme. Setting: whole-section overrides. Recovery: edit palette only, duplicate the theme, or update the composer table."
            color: Color.urgent; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall
        }
        Text {
            Layout.fillWidth: true
            visible: root.recovering
            text: "A shell preview recovery is open. File: transaction journal. Setting: running shell theme. Recovery: stop the preview from History to restore colors.toml and shell.toml."
            color: Color.urgent; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall
        }
        Text {
            Layout.fillWidth: true
            visible: root.emptyState
            text: "No themes found. File: ~/.config/omarchy/themes/. Setting: theme inventory. Recovery: create a minimal dark or light theme below."
            color: Color.muted; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall
        }

        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: Style.spacing.md

            ColumnLayout {
                Layout.preferredWidth: Style.space(150); Layout.fillHeight: true; spacing: Style.spacing.xs
                Ui.Button { id: paletteTab; Layout.fillWidth: true; text: "Palette"; focusable: true; selected: root.selectedTab === "palette"; onClicked: root.selectedTab = "palette" }
                Ui.Button { Layout.fillWidth: true; text: "Surfaces"; focusable: true; selected: root.selectedTab === "surfaces"; onClicked: root.selectedTab = "surfaces" }
                Ui.Button { Layout.fillWidth: true; text: "Type and spacing"; focusable: true; selected: root.selectedTab === "type"; onClicked: root.selectedTab = "type" }
                Ui.Button { Layout.fillWidth: true; text: "Bar"; focusable: true; selected: root.selectedTab === "bar"; onClicked: root.selectedTab = "bar" }
                Ui.Button { Layout.fillWidth: true; text: "Wallpapers"; focusable: true; selected: root.selectedTab === "wallpapers"; onClicked: root.selectedTab = "wallpapers" }
                Ui.Button { Layout.fillWidth: true; text: "Diagnostics"; focusable: true; selected: root.selectedTab === "diagnostics"; onClicked: root.selectedTab = "diagnostics" }
                Ui.Button { Layout.fillWidth: true; text: "Themes"; focusable: true; selected: root.selectedTab === "themes"; onClicked: root.selectedTab = "themes" }
                Item { Layout.fillHeight: true }
                Ui.Button { Layout.fillWidth: true; text: "Reset"; focusable: true; enabled: !root.busy; onClicked: root.requestReset() }
                Ui.Button { Layout.fillWidth: true; text: "Review changes"; focusable: true; enabled: !root.busy && !root.composeUnavailable; onClicked: root.requestPlan() }
            }

            Ui.BorderSurface {
                Layout.fillWidth: true; Layout.fillHeight: true
                color: Color.popups.background; borderSpec: Border.surfaceSpec("popups", "border")
                Loader {
                    anchors.fill: parent; anchors.margins: Style.spacing.lg
                    sourceComponent: root.selectedTab === "palette" ? paletteComponent
                                     : root.selectedTab === "wallpapers" ? wallpaperComponent
                                     : root.selectedTab === "diagnostics" ? diagnosticsComponent
                                     : root.selectedTab === "themes" ? themesComponent : sectionComponent
                }
            }

            PreviewCanvas {
                Layout.preferredWidth: parent.width * 0.4; Layout.fillHeight: true
                payload: root.previewPayload; loading: root.previewLoading; errorText: root.previewError
            }
        }
    }

    Component {
        id: paletteComponent
        PaletteEditor { draft: root.draft; busy: root.busy; onPatchRequested: patch => root.requestDraftPatch(patch) }
    }
    Component {
        id: wallpaperComponent
        WallpaperList { wallpapers: root.draft && root.draft.wallpapers ? root.draft.wallpapers : []; busy: root.busy; onPatchRequested: patch => root.requestDraftPatch(patch) }
    }
    Component {
        id: diagnosticsComponent
        DiagnosticsPanel { payload: root.previewPayload; errorText: root.previewError }
    }
    Component {
        id: themesComponent
        SectionEditor { title: "Installed themes"; message: "File: ~/.config/omarchy/themes/<slug>/. Setting: activate, duplicate, or delete. Recovery: duplicate read-only Git and symlink themes before editing." }
    }
    Component {
        id: sectionComponent
        SectionEditor { title: root.selectedTab === "type" ? "Type and spacing" : root.selectedTab === "bar" ? "Bar" : "Surfaces"; message: "Whole-section overrides are edited as a complete set. Inherit keeps the generated shell.toml defaults." }
    }
}
