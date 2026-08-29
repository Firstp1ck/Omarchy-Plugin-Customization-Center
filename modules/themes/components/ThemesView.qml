import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons
import "preview/PreviewResolver.js" as PreviewResolver

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
    property string selectedSection: "controls"
    property var previewPayload: null
    property string previewError: ""
    property bool previewLoading: false
    property bool effectivePreview: true
    property bool previewOutdated: false
    property var pendingPayload: null
    readonly property var statusData: status && status.data ? status.data : ({})
    readonly property var openPreview: statusData.openPreviewTransaction || null

    function capability(name) {
        var items = capabilities && capabilities.items ? capabilities.items : []
        for (var index = 0; index < items.length; ++index) if (items[index].name === name) return items[index]
        return ({ available: true, reason: "" })
    }
    function focusFirst() { paletteTab.forceActiveFocus() }
    function actionPatch(kind, slug) {
        return { schemaVersion: 1, kind: kind, slug: slug, palette: null, sections: null, wallpapers: null,
            displayName: null, origin: null, iconTheme: null, activate: null, tryInShell: null,
            delete: kind === "compose" ? true : null, acceptedWarnings: [] }
    }
    function handlePayload(payload) {
        pendingPayload = payload || ({})
        if (payload && typeof payload.tab === "string" && ["palette", "surfaces", "type", "bar", "wallpapers", "diagnostics", "themes"].indexOf(payload.tab) >= 0) selectedTab = payload.tab
        if (payload && typeof payload.slug === "string") { selectedTab = "themes"; importTheme(payload.slug, "") }
        if (payload && typeof payload.activate === "string") { selectedTab = "themes"; requestDraftPatch(actionPatch("activate", payload.activate)) }
    }
    function patchSection(name, value) { var changed = ({}); changed[name] = value; requestDraftPatch({ sections: changed }) }
    function importTheme(slug, duplicateSlug) {
        if (!backendClient) return
        backendClient.query(moduleId, "import", { slug: slug, duplicateSlug: duplicateSlug || null }, function(result) {
            if (result && result.ok && result.data && result.data.draft) {
                var imported = result.data.draft; imported.activate = false; imported.delete = false; imported.tryInShell = false
                root.requestDraftPatch(imported); root.selectedTab = "palette"
            } else root.previewError = result && result.error ? String(result.error.message || result.error.code) : "Theme import failed"
        })
    }
    function requestLocalPreview() {
        if (!draft || draft.kind !== "compose" || draft.delete === true || !draft.palette) return
        try {
            var machine = statusData.machineOverride ? statusData.machineOverride.values : ({})
            previewPayload = { tokens: PreviewResolver.resolve(draft, machine, { effective: effectivePreview }) }
            previewError = ""
        } catch (error) { previewError = String(error) }
    }
    function requestPreview() {
        requestLocalPreview()
        if (!backendClient || !draft || draft.kind !== "compose" || draft.delete === true) return
        previewLoading = true
        backendClient.query(moduleId, "preview", { draft: draft, portable: !effectivePreview }, function(result) {
            previewLoading = false
            if (result && result.ok && result.data) previewPayload = result.data
            else previewError = result && result.error ? String(result.error.message || result.error.code) : "Preview query failed"
        })
    }
    function patchThenPlan(patch) {
        requestDraftPatch(patch)
        Qt.callLater(function() { root.requestPlan() })
    }
    function activateTheme(slug) { patchThenPlan(actionPatch("activate", slug)) }
    function deleteTheme(slug) { patchThenPlan(actionPatch("compose", slug)) }
    function startShellPreview() { patchThenPlan({ activate: false, delete: false, tryInShell: true }) }
    function stopShellPreview(afterRestore) {
        if (!backendClient || !openPreview) return
        backendClient.rollback(openPreview.transactionId, "user", function(result) {
            if (!result || !result.ok) {
                previewError = result && result.error ? result.error.message : "Shell preview restore failed"
                return
            }
            if (afterRestore) afterRestore()
        })
    }
    function updateShellPreview() {
        stopShellPreview(function() {
            root.previewOutdated = false
            root.startShellPreview()
        })
    }
    function defaultsFor(name) {
        var source = PreviewResolver.sectionDefaults[name] || ({})
        var value = JSON.parse(JSON.stringify(source))
        Object.keys(value).forEach(function(key) { if (value[key] === "red" && root.draft && root.draft.palette) value[key] = root.draft.palette.red })
        if (name === "lock" && value.placeholder === null && previewPayload && previewPayload.tokens) value.placeholder = previewPayload.tokens.sections.lock.placeholder
        return value
    }
    function fieldsFor(name) {
        var values = defaultsFor(name); var output = []
        var nullableNumeric = name === "font" || name === "spacing"
        Object.keys(values).forEach(function(key) {
            var value = values[key]; var type = "string"
            if (typeof value === "boolean") type = "boolean"
            else if (typeof value === "number") type = Number.isInteger(value) && key.indexOf("alpha") < 0 && key !== "scale" ? "integer" : "number"
            else if (value === null) type = nullableNumeric ? "nullable-integer" : "nullable-string"
            output.push({ key: key, label: key.split("-").join(" "), type: type,
                placeholder: key.indexOf("width") >= 0 ? "1 or 2 2 2 4" : key.indexOf("color") >= 0 || ["background","text","active","accent","scrim","selection","placeholder","countdown"].indexOf(key) >= 0 ? "role or #rrggbb" : "" })
        })
        return output
    }

    onDraftChanged: { if (openPreview) previewOutdated = true; requestLocalPreview(); previewTimer.restart() }
    onStatusChanged: { previewOutdated = false; requestLocalPreview(); previewTimer.restart() }
    onEffectivePreviewChanged: { requestLocalPreview(); previewTimer.restart() }
    Timer { id: previewTimer; interval: 120; repeat: false; onTriggered: root.requestPreview() }

    readonly property bool composeUnavailable: !capability("compose").available
    readonly property bool unsupported: status && status.warnings && status.warnings.length > 0
    readonly property bool emptyState: statusData.themes && statusData.themes.length === 0

    ColumnLayout {
        anchors.fill: parent; anchors.margins: Style.spacing.panelPadding; spacing: Style.spacing.md
        visible: root.status !== null
        Text { Layout.fillWidth: true; text: "Theme composer"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading; font.bold: true }
        Ui.BorderSurface {
            Layout.fillWidth: true; visible: root.composeUnavailable; color: Color.popups.background; borderSpec: Border.surfaceSpec("notifications", "border"); implicitHeight: unavailableText.implicitHeight + Style.spacing.xl * 2
            Text { id: unavailableText; anchors.fill: parent; anchors.margins: Style.spacing.xl; text: "Theme composition unavailable: " + root.capability("compose").reason + "\nFile: $OMARCHY_PATH/default/themed/shell.toml.tpl\nRecovery: restore the Omarchy template and retry."; color: Color.urgent; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.body }
        }
        Text { Layout.fillWidth: true; visible: root.unsupported; text: "Template drift detected. Palette editing and activation remain available; section output requires review."; color: Color.urgent; wrapMode: Text.WordWrap; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
        TryInShellBanner { Layout.fillWidth: true; visible: root.openPreview !== null; transactionId: root.openPreview ? root.openPreview.transactionId : ""; outdated: root.previewOutdated; onStopRequested: root.stopShellPreview(); onUpdateRequested: root.updateShellPreview() }
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
                RowLayout {
                    Layout.fillWidth: true
                    Text { Layout.fillWidth: true; text: "Effective here"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
                    Ui.ToggleSwitch { checked: root.effectivePreview; Accessible.name: "Include machine shell overrides"; onToggled: root.effectivePreview = !checked }
                }
                Ui.Button { Layout.fillWidth: true; text: root.openPreview ? "Preview active" : "Try in shell"; focusable: true; enabled: !root.busy && !root.openPreview && root.capability("tryInShell").available; onClicked: root.startShellPreview() }
                Ui.Button { Layout.fillWidth: true; text: "Reset"; focusable: true; enabled: !root.busy; onClicked: root.requestReset() }
                Ui.Button { Layout.fillWidth: true; text: "Save"; focusable: true; enabled: !root.busy && root.draft.kind === "compose"; onClicked: root.patchThenPlan({ activate: false, tryInShell: false }) }
                Ui.Button { Layout.fillWidth: true; text: "Save and activate"; focusable: true; enabled: !root.busy && root.draft.kind === "compose"; onClicked: root.patchThenPlan({ activate: true, tryInShell: false }) }
                Ui.Button { Layout.fillWidth: true; text: "Review changes"; focusable: true; enabled: !root.busy; onClicked: root.requestPlan() }
            }
            Ui.BorderSurface {
                Layout.fillWidth: true; Layout.fillHeight: true; color: Color.popups.background; borderSpec: Border.surfaceSpec("popups", "border")
                Loader { anchors.fill: parent; anchors.margins: Style.spacing.lg; sourceComponent: root.selectedTab === "palette" ? paletteComponent : root.selectedTab === "wallpapers" ? wallpaperComponent : root.selectedTab === "diagnostics" ? diagnosticsComponent : root.selectedTab === "themes" ? themesComponent : sectionComponent }
            }
            PreviewCanvas { Layout.preferredWidth: parent.width * 0.4; Layout.fillHeight: true; payload: root.previewPayload; loading: root.previewLoading; errorText: root.previewError }
        }
    }
    Text { anchors.centerIn: parent; visible: root.status === null; text: "Loading themes.\nFile: ~/.config/omarchy/themes/<slug>/colors.toml\nRecovery: wait, then retry status."; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; horizontalAlignment: Text.AlignHCenter }

    Component { id: paletteComponent; PaletteEditor { draft: root.draft; busy: root.busy; onPatchRequested: patch => root.requestDraftPatch(patch) } }
    Component { id: wallpaperComponent; WallpaperList { wallpapers: root.draft && root.draft.wallpapers ? root.draft.wallpapers : []; preferred: root.draft && root.draft.preferredWallpaper ? root.draft.preferredWallpaper : ""; busy: root.busy; onPatchRequested: patch => root.requestDraftPatch(patch) } }
    Component { id: diagnosticsComponent; DiagnosticsPanel { payload: root.previewPayload; errorText: root.previewError } }
    Component {
        id: themesComponent
        InstalledThemes { themes: root.statusData.themes || []; activeSlug: root.statusData.active ? root.statusData.active.slug || "" : ""; busy: root.busy; onActivateRequested: slug => root.activateTheme(slug); onOpenRequested: slug => root.importTheme(slug, ""); onDuplicateRequested: (slug, newSlug) => root.importTheme(slug, newSlug); onDeleteRequested: slug => root.deleteTheme(slug) }
    }
    Component {
        id: sectionComponent
        ColumnLayout {
            spacing: Style.spacing.sm
            Ui.Dropdown { visible: root.selectedTab === "surfaces"; Layout.fillWidth: true; value: root.selectedSection; options: ["controls","popups","tooltip","notifications","launcher","menu","polkit","lock","image-picker"]; onChanged: value => root.selectedSection = value }
            Ui.Dropdown { visible: root.selectedTab === "type"; Layout.fillWidth: true; value: root.selectedSection === "font" || root.selectedSection === "spacing" ? root.selectedSection : "font"; options: ["font","spacing"]; onChanged: value => root.selectedSection = value }
            SectionEditor {
                Layout.fillWidth: true; Layout.fillHeight: true
                sectionName: root.selectedTab === "bar" ? "bar" : root.selectedTab === "type" ? (root.selectedSection === "spacing" ? "spacing" : "font") : root.selectedSection
                title: sectionName.split("-").join(" ")
                value: root.draft && root.draft.sections ? root.draft.sections[sectionName] : null
                defaults: root.defaultsFor(sectionName); fields: root.fieldsFor(sectionName); busy: root.busy
                message: "Every customized section is complete and typed; inherit writes no fragment."
                onSectionRequested: (name, value) => root.patchSection(name, value)
            }
        }
    }
}
