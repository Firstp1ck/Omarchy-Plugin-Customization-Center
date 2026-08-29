import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui
import "components" as Bar

FocusScope {
    id: root
    objectName: "barPage"
    property string moduleId: "bar"
    property var status: null
    property var capabilities: ({})
    property var draft: ({})
    property bool busy: false
    property var backendClient: null
    property string selectedKey: ""
    property string toastText: ""
    property string selectedPresetId: ""
    property string presetName: ""

    signal requestPlan()
    signal requestApply()
    signal requestReset()
    signal requestDraftPatch(var patch)
    signal requestNavigate(string moduleId, var payload)

    readonly property var statusData: status && status.data ? status.data : ({})
    readonly property var activeDraft: root["draft"] && root["draft"].schemaVersion === 1 ? root["draft"] : baseDraft()
    readonly property var bar: activeDraft.bar || ({ layout: ({ left: [], center: [], right: [] }) })
    readonly property var catalog: statusData.catalog || []
    readonly property string pageState: status === null ? "loading"
        : statusData.shell && statusData.shell.available !== true ? "shell-unavailable"
        : statusData.file && statusData.file.exists && (statusData.file.parses !== true || statusData.file.version1 !== true) ? "load-error"
        : statusData.shell && statusData.shell.scanning ? "scanning"
        : activeDraft.baseRevision !== status.revision ? "stale"
        : statusData.shell && statusData.shell.fallback ? "fallback" : "ready"

    function copy(value) { return JSON.parse(JSON.stringify(value)) }
    function baseDraft() {
        var source = statusData.bar || ({ id: null, position: "top", transparent: false, centerAnchor: "", extra: ({}), layout: ({ left: [], center: [], right: [] }) })
        var next = copy(source); var serial = 0; var sections = ["left", "center", "right"]
        for (var s = 0; s < sections.length; ++s) {
            var section = sections[s]; var values = next.layout[section] || []
            for (var i = 0; i < values.length; ++i) { serial++; values[i].key = "d:" + serial; values[i].origin = ({ section: section, index: i }) }
        }
        return ({ schemaVersion: 1, module: "bar", baseRevision: status ? status.revision : statusData.revision || "",
            action: "apply", presetId: null, presetName: null, bar: next })
    }
    function emitDraft(next) {
        next.action = "apply"; next.presetId = null; next.presetName = null
        requestDraftPatch(next)
    }
    function updateBar(key, value) { var next = copy(activeDraft); next.bar[key] = value; emitDraft(next) }
    function locate(key) {
        var sections = ["left", "center", "right"]
        for (var s = 0; s < sections.length; ++s) for (var i = 0; i < (bar.layout[sections[s]] || []).length; ++i)
            if (bar.layout[sections[s]][i].key === key) return ({ section: sections[s], index: i, entry: bar.layout[sections[s]][i] })
        return null
    }
    function catalogItem(id) { for (var i = 0; i < catalog.length; ++i) if (catalog[i].id === id) return catalog[i]; return null }
    function applyLayout(layout) { var next = copy(activeDraft); next.bar.layout = copy(layout); emitDraft(next) }
    function addWidget(item) {
        if (!item || item.presence !== "shell") return
        var next = copy(activeDraft); var section = item.defaultSection || "center"; var values = next.bar.layout[section]
        if (!item.allowMultiple) for (var i = 0; i < values.length; ++i) if (values[i].id === item.id) { selectedKey = values[i].key; return }
        var entry = ({ key: "d:" + Date.now(), origin: null, id: item.id, settings: copy(item.defaults || ({})), form: "object" })
        values.push(entry); selectedKey = entry.key; emitDraft(next)
    }
    function removeSelected() { if (!selectedKey) return; reorder.remove(selectedKey); selectedKey = "" }
    function editSetting(key, value) {
        var location = locate(selectedKey); if (!location) return
        var next = copy(activeDraft); next.bar.layout[location.section][location.index].settings[key] = value; emitDraft(next)
    }
    function duplicateSelected() {
        var location = locate(selectedKey); if (!location) return
        var item = catalogItem(location.entry.id); if (!item || !item.allowMultiple) return
        var next = copy(activeDraft); var duplicate = copy(location.entry); duplicate.key = "d:" + Date.now(); duplicate.origin = null
        next.bar.layout[location.section].splice(location.index + 1, 0, duplicate); selectedKey = duplicate.key; emitDraft(next)
    }
    function loadBar(value) { var next = copy(activeDraft); next.bar = copy(value); emitDraft(next) }
    function selectedPreset() {
        var presets = statusData.presets || []
        for (var i = 0; i < presets.length; ++i) if (presets[i].id === selectedPresetId) return presets[i]
        return null
    }
    function loadPreset() { var preset = selectedPreset(); if (preset) loadBar(preset.barModel || preset.bar) }
    function savePreset() {
        if (!selectedPresetId || !presetName.trim()) return
        var next = copy(activeDraft); next.action = "save-preset"; next.presetId = selectedPresetId; next.presetName = presetName.trim()
        requestDraftPatch(next); Qt.callLater(function() { root.requestPlan() })
    }
    function deletePreset() {
        if (!selectedPreset()) return
        var next = copy(activeDraft); next.action = "delete-preset"; next.presetId = selectedPresetId; next.presetName = null
        requestDraftPatch(next); Qt.callLater(function() { root.requestPlan() })
    }
    function focusFirst() { options.focusFirst() }
    function handlePayload(payload) {
        if (!payload) return
        if (payload.select && typeof payload.select.section === "string") {
            var sections = ["left", "center", "right"]
            for (var s = 0; s < sections.length; ++s) for (var i = 0; i < (bar.layout[sections[s]] || []).length; ++i) {
                var origin = bar.layout[sections[s]][i].origin
                if (origin && origin.section === payload.select.section && origin.index === payload.select.index) {
                    selectedKey = bar.layout[sections[s]][i].key; preview.forceActiveFocus(); return
                }
            }
        }
        if (typeof payload.selectBar === "string") {
            var found = false
            for (var b = 0; b < (statusData.barOptions || []).length; ++b) if (statusData.barOptions[b].id === payload.selectBar && statusData.barOptions[b].available) found = true
            if (found) updateBar("id", payload.selectBar === "omarchy.bar" ? null : payload.selectBar)
            else toastText = "Bar option is not available: " + payload.selectBar
            options.focusFirst()
        }
    }

    Bar.ReorderController { id: reorder; layout: root.bar.layout || ({ left: [], center: [], right: [] }); onMoved: (key, section, index, layout) => root.applyLayout(layout); onRemoved: (key, layout) => root.applyLayout(layout) }

    ColumnLayout {
        anchors.fill: parent; spacing: Style.spacing.panelGap
        RowLayout { Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: "Bar"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading }
            Text { objectName: "barStatusChip"; text: pageState === "fallback" ? "Configured " + statusData.shell.configuredBarId + ", running " + statusData.shell.activeBarId : pageState; color: pageState === "ready" ? Color.foreground : Color.urgent; font.family: Style.font.family }
            Ui.Button { text: "Reset"; enabled: !root.busy; onClicked: root.requestReset() }
            Ui.Button { objectName: "reviewButton"; text: "Review"; enabled: !root.busy && ["ready", "fallback"].indexOf(root.pageState) >= 0; onClicked: root.requestPlan() }
        }
        Text { visible: ["shell-unavailable", "load-error", "scanning", "stale"].indexOf(pageState) >= 0; Layout.fillWidth: true; wrapMode: Text.WordWrap; text: pageState === "shell-unavailable" ? "The Omarchy shell is unavailable. Editing and draft saving remain available; Apply is refused." : pageState === "load-error" ? "shell.json is malformed or not version 1. Repair the file before Apply." : pageState === "scanning" ? "Plugin scan in progress." : "The bar changed since this draft was created. Reload or compare before Apply."; color: Color.urgent; font.family: Style.font.family }
        Bar.BarOptions { id: options; Layout.fillWidth: true; bar: root.bar; barOptions: statusData.barOptions || []; centerIds: (root.bar.layout.center || []).map(function(item) { return item.id }); busy: root.busy; onOptionChanged: (key, value) => root.updateBar(key, value) }
        RowLayout {
            Layout.fillWidth: true; spacing: Style.spacing.sm
            Ui.Button { text: "Load Omarchy defaults"; focusable: true; enabled: !root.busy && !!statusData.defaults; onClicked: root.loadBar(statusData.defaults) }
            Ui.Dropdown { objectName: "presetSelector"; Layout.preferredWidth: 180; value: root.selectedPresetId; options: [""].concat((statusData.presets || []).map(function(item) { return item.id })); onChanged: value => root.selectedPresetId = value }
            Ui.TextField { objectName: "presetName"; Layout.preferredWidth: 180; text: root.presetName; placeholderText: "Preset name"; onTextChanged: root.presetName = text }
            Ui.Button { text: "Load preset"; focusable: true; enabled: !root.busy && !!root.selectedPreset(); onClicked: root.loadPreset() }
            Ui.Button { text: "Save preset"; focusable: true; enabled: !root.busy && root.selectedPresetId.length > 0 && root.presetName.trim().length > 0; onClicked: root.savePreset() }
            Ui.Button { text: "Delete preset"; focusable: true; enabled: !root.busy && !!root.selectedPreset(); onClicked: root.deletePreset() }
        }
        Bar.BarPreview { id: preview; Layout.fillWidth: true; bar: root.bar; catalog: root.catalog; selectedKey: root.selectedKey; onSelected: key => root.selectedKey = key; onMoveRequested: (key, section, index) => reorder.move(key, section, index); onRemoveRequested: key => { root.selectedKey = key; root.removeSelected() } }
        RowLayout { Layout.fillWidth: true; Layout.fillHeight: true; spacing: Style.spacing.panelGap
            Bar.WidgetCatalog { Layout.preferredWidth: 280; Layout.fillHeight: true; catalog: root.catalog; onAddRequested: item => root.addWidget(item) }
            Bar.WidgetInspector {
                Layout.fillWidth: true
                Layout.fillHeight: true
                entry: {
                    var found = root.locate(root.selectedKey)
                    return found ? found.entry : null
                }
                catalogItem: entry ? root.catalogItem(entry.id) : null
                busy: root.busy
                onSettingChanged: (key, value) => root.editSetting(key, value)
                onRemoveRequested: root.removeSelected()
            }
        }
        Text { visible: toastText.length > 0; text: toastText; color: Color.urgent; font.family: Style.font.family }
    }
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Delete && selectedKey) { removeSelected(); event.accepted = true }
        else if (event.key === Qt.Key_D && (event.modifiers & Qt.ControlModifier)) { duplicateSelected(); event.accepted = true }
        else if (event.key === Qt.Key_Escape) { if (reorder.grabbedKey) reorder.cancel(); else selectedKey = ""; event.accepted = true }
        else if (event.key === Qt.Key_Space && selectedKey) { if (reorder.grabbedKey) reorder.drop(); else reorder.grab(selectedKey); event.accepted = true }
    }
}
