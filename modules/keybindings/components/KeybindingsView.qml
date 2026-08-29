import QtQuick
import QtQuick.Layouts
import qs.Ui as Ui
import qs.Commons

Item {
    id: root
    property string moduleId: "keybindings"
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

    readonly property var effective: status && status.data ? status.data : (status || ({}))
    readonly property var rows: effective.records || []
    readonly property var activeModel: draft && draft.model ? draft.model : (effective.model || ({ schemaVersion: 1, bindings: [], disabled: [] }))
    readonly property var editCapability: effective.capabilities && effective.capabilities.edit ? effective.capabilities.edit : ({ available: false, reasons: ["loading"] })
    property string filter: "All"
    property var selectedRow: null
    property string stateMessage: ""
    property var lastPayload: null
    property string editorMode: "add"
    property string editingId: ""
    property var replacementRow: null
    property var editorChord: null
    property bool editorOpen: false
    property string editorCatalogId: ""
    property var editorFlags: ({ locked: false, release: false, repeating: false, nonConsuming: false, autoConsuming: false, bypass: false })
    readonly property bool driftMode: effective.managedBlock && effective.managedBlock.drift === true
    onDriftModeChanged: if (driftMode) editorOpen = false

    function focusFirst() { search.forceActiveFocus() }
    function handlePayload(payload) {
        lastPayload = payload || ({})
        if (payload && payload.select) {
            search.text = String(payload.select)
            search.queryEdited(search.text)
        }
        if (payload && payload.action === "add") {
            startAdd()
            chord.setValueAndNormalize(String(payload.chord || ""))
            action.command = String(payload.command || "")
        }
    }
    function cloneModel() { return JSON.parse(JSON.stringify(activeModel)) }
    function revision() { return status ? String(status.revision || effective.revision || "") : "" }
    function patchModel(model, recoveryAction) {
        var patch = { schemaVersion: 1, expectedRevision: revision(), model: model }
        if (recoveryAction) patch.recoveryAction = recoveryAction
        requestDraftPatch(patch)
    }
    function uuid() {
        var template = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx"
        return template.replace(/[xy]/g, function(c) {
            var r = Math.floor(Math.random() * 16)
            var v = c === "x" ? r : (r & 3) | 8
            return v.toString(16)
        })
    }
    function defaultFlags() { return ({ locked: false, release: false, repeating: false, nonConsuming: false, autoConsuming: false, bypass: false }) }
    function startAdd() {
        editorMode = "add"; editingId = ""; replacementRow = null; editorChord = null; editorCatalogId = ""
        editorFlags = defaultFlags(); chord.setValueAndNormalize(""); action.command = ""; description.text = ""; editorOpen = true; chord.focusInput()
    }
    function startEdit(row) {
        var item = (activeModel.bindings || []).filter(function(value) { return value.id === row.managedId })[0]
        if (!item) return
        editorMode = "edit"; editingId = item.id; replacementRow = null; editorChord = null
        chord.setValueAndNormalize(item.chord.sourceKeys)
        action.command = item.action.command; editorCatalogId = item.action.catalogId || ""; description.text = item.description
        editorFlags = JSON.parse(JSON.stringify(item.flags)); editorOpen = true; chord.focusInput()
    }
    function chordFromSource(source, keyToken) {
        var parts = String(source).split("+").map(function(value) { return value.trim() })
        var key = keyToken || parts[parts.length - 1]
        var modifiers = parts.slice(0, parts.length - 1)
        var code = String(key).match(/^code:(\d+)$/)
        return { sourceKeys: source, modifiers: modifiers,
                 key: code ? { kind: "code", value: Number(code[1]) } : { kind: "keysym", value: key.length === 1 ? key.toLowerCase() : key } }
    }
    function startReplace(row) {
        editorMode = "replace"; editingId = ""; replacementRow = row; editorChord = null
        chord.setValueAndNormalize(row.catalog.keys); action.command = ""; editorCatalogId = ""; description.text = row.description
        editorFlags = defaultFlags(); editorOpen = true; chord.focusInput()
    }
    function bindingFrom(normalized, descriptionValue, commandValue, catalogId, flags, idValue) {
        return { id: idValue || uuid(), enabled: true,
                 chord: { sourceKeys: normalized.sourceKeys, modifiers: normalized.modifiers || [], key: normalized.key },
                 description: descriptionValue, action: { type: "exec", command: commandValue, catalogId: catalogId || null },
                 flags: JSON.parse(JSON.stringify(flags || defaultFlags())) }
    }
    function addBinding(normalized, descriptionValue, commandValue, catalogId, flags) {
        var model = cloneModel(); model.bindings = model.bindings || []
        model.bindings.push(bindingFrom(normalized, descriptionValue, commandValue, catalogId, flags, "")); patchModel(model)
    }
    function editBinding(idValue, normalized, descriptionValue, commandValue, catalogId, flags) {
        var model = cloneModel()
        model.bindings = (model.bindings || []).map(function(item) { return item.id === idValue ? bindingFrom(normalized, descriptionValue, commandValue, catalogId, flags, idValue) : item })
        patchModel(model)
    }
    function disableDefault(row, reason, replacedBy) {
        var model = cloneModel(); model.disabled = model.disabled || []
        model.disabled.push({ id: uuid(), sourceKeys: row.catalog.keys,
                              target: { kind: "omarchy_default", module: row.catalog.module,
                                        description: row.description, identity: row.identity },
                              reason: reason || "disabled", replacedBy: replacedBy || null })
        patchModel(model); return model
    }
    function replaceDefault(row, normalized, descriptionValue, commandValue, catalogId, flags) {
        var model = cloneModel(); var binding = bindingFrom(normalized, descriptionValue, commandValue, catalogId, flags, "")
        model.bindings = model.bindings || []; model.bindings.push(binding); model.disabled = model.disabled || []
        model.disabled.push({ id: uuid(), sourceKeys: row.catalog.keys,
                              target: { kind: "omarchy_default", module: row.catalog.module,
                                        description: row.description, identity: row.identity },
                              reason: "replaced", replacedBy: binding.id })
        patchModel(model)
    }
    function removeManaged(row) {
        var model = cloneModel()
        model.bindings = (model.bindings || []).filter(function(item) { return item.id !== row.managedId })
        patchModel(model)
    }
    function commitEditor() {
        var normalized = chord.normalized
        if (!normalized || chord.normalizedText !== chord.value || !normalized.key || description.text.length === 0 || action.command.length === 0) { stateMessage = "A current normalized chord, description, and command are required"; return }
        if (editorMode === "edit") editBinding(editingId, normalized, description.text, action.command, editorCatalogId, editorFlags)
        else if (editorMode === "replace") replaceDefault(replacementRow, normalized, description.text, action.command, editorCatalogId, editorFlags)
        else addBinding(normalized, description.text, action.command, editorCatalogId, editorFlags)
        editorOpen = false
    }
    function rewriteDrift() { patchModel(cloneModel(), "rewrite") }
    function forgetManaged() { patchModel(cloneModel(), "forget") }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Style.spacing.panelPadding
        spacing: Style.spacing.md

        RowLayout {
            Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: "Keybindings"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading; font.bold: true }
            Ui.Button { objectName: "addBindingButton"; text: "Add binding"; focusable: true; visible: !root.driftMode; enabled: root.editCapability.available && !root.busy; onClicked: root.startAdd() }
        }

        Ui.TextField {
            id: search
            objectName: "bindingSearchField"
            Layout.fillWidth: true
            visible: !root.driftMode
            placeholderText: "Search chord, description, action, or source"
            onTextEdited: table.searchText = text
        }

        RowLayout {
            objectName: "bindingFilterControls"
            Layout.fillWidth: true
            visible: !root.driftMode
            Repeater {
                model: ["All", "Omarchy defaults", "Managed", "Other", "Pointer and switches", "Read-only"]
                delegate: Ui.Button {
                    required property string modelData
                    text: modelData
                    focusable: true
                    selected: root.filter === modelData
                    onClicked: root.filter = modelData
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            visible: root.status === null || !root.editCapability.available || (root.effective.managedBlock && root.effective.managedBlock.drift) || root.rows.length === 0
            implicitHeight: bannerText.implicitHeight + Style.spacing.panelPadding * 2
            color: Style.normalFill
            border.color: (root.status !== null && !root.editCapability.available) ? Color.urgent : Style.normalBorderColor
            border.width: Style.normalBorderWidth
            radius: Style.cornerRadius
            Text {
                id: bannerText
                objectName: "statusBannerText"
                anchors.fill: parent
                anchors.margins: Style.spacing.panelPadding
                color: Color.foreground
                font.family: Style.font.family
                font.pixelSize: Style.font.body
                wrapMode: Text.WordWrap
                text: {
                    if (root.status === null) return "Loading active keybindings from hyprctl. File: ~/.config/hypr/bindings.lua. Setting: global bindings. Recovery: wait, then retry status."
                    if (root.effective.managedBlock && root.effective.managedBlock.drift) return "Recovery required: the managed keybinding setting in ~/.config/hypr/bindings.lua differs from keybindings.json. Review and rewrite the block from the stored model, or restore a transaction backup."
                    if (!root.editCapability.available) return "Keybinding editing is unavailable for ~/.config/hypr/bindings.lua. Setting: managed global bindings. Recovery: " + String((root.editCapability.reasons || []).join(", ")) + "; install luac, run omarchy-refresh-config hypr/bindings.lua, repair markers, or start Hyprland as applicable."
                    return "No active bindings were reported. File: ~/.config/hypr/bindings.lua. Setting: compositor inventory. Recovery: start Hyprland and retry hyprctl binds."
                }
            }
        }

        RowLayout {
            id: driftActions
            objectName: "driftActions"
            Layout.fillWidth: true
            visible: root.driftMode
            Text { Layout.fillWidth: true; text: "Choose one recovery action for ~/.config/hypr/bindings.lua."; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
            Ui.Button { objectName: "rewriteDriftButton"; text: "Rewrite block from JSON"; focusable: true; enabled: !root.busy; onClicked: root.rewriteDrift() }
            Ui.Button { objectName: "forgetDriftButton"; text: "Forget managed records"; focusable: true; enabled: !root.busy; onClicked: root.forgetManaged() }
        }

        ColumnLayout {
            id: editor
            objectName: "editorForm"
            Layout.fillWidth: true
            visible: root.editorOpen && !root.driftMode
            spacing: Style.spacing.md
            ChordField { id: chord; objectName: "chordField"; Layout.fillWidth: true; backendClient: root.backendClient; moduleId: root.moduleId; parentBusy: root.busy; onCaptureRequested: capture.openCapture(); onChordEdited: function(value, normalized) { root.editorChord = normalized } }
            Ui.TextField { id: description; Layout.fillWidth: true; placeholderText: "Description" }
            ActionPicker { id: action; Layout.fillWidth: true; backendClient: root.backendClient; moduleId: root.moduleId; onCommandEdited: function(command, catalogId) { root.editorCatalogId = catalogId } }
            RowLayout {
                Layout.fillWidth: true
                Repeater {
                    model: [{ key: "locked", label: "Locked", help: "Works while input is inhibited" }, { key: "release", label: "Release", help: "Runs when the key is released" }, { key: "repeating", label: "Repeat", help: "Repeats while the key is held" }, { key: "nonConsuming", label: "Non-consuming", help: "Passes the event to applications" }, { key: "autoConsuming", label: "Auto-consuming", help: "Consumes only when the dispatcher handles it" }, { key: "bypass", label: "Bypass", help: "Works through shortcut inhibition" }]
                    delegate: Ui.Button {
                        required property var modelData
                        text: modelData.label
                        tooltipText: modelData.help
                        focusable: true
                        selected: root.editorFlags[modelData.key] === true
                        onClicked: {
                            var next = Object.assign({}, root.editorFlags)
                            next[modelData.key] = !next[modelData.key]
                            root.editorFlags = next
                        }
                    }
                }
            }
            Text { Layout.fillWidth: true; text: "This form edits the draft only. The command runs as your user and is stored as plain text."; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                Ui.Button { text: "Cancel"; focusable: true; onClicked: root.editorOpen = false }
                Ui.Button { objectName: "saveBindingButton"; text: root.editorMode === "edit" ? "Save binding" : (root.editorMode === "replace" ? "Replace default" : "Add binding"); focusable: true; enabled: !root.busy && chord.normalized !== null && chord.normalizedText === chord.value && description.text.length > 0 && action.command.length > 0; onClicked: root.commitEditor() }
            }
        }

        RowLayout {
            objectName: "bindingTableRegion"
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !root.driftMode
            BindingTable {
                id: table
                objectName: "bindingTable"
                visible: !root.driftMode
                Layout.fillWidth: true
                Layout.fillHeight: true
                rows: root.rows
                filter: root.filter
                onRowActivated: function(row) { root.selectedRow = row }
            }
            BindingDetails {
                Layout.preferredWidth: Style.space(360)
                Layout.fillHeight: true
                row: root.selectedRow
                onEditRequested: function(row) { root.startEdit(row) }
                onRemoveRequested: function(row) { root.removeManaged(row) }
                onDisableRequested: function(row) { root.disableDefault(row, "disabled", null) }
                onReplaceRequested: function(row) { root.startReplace(row) }
            }
        }

        ConflictPanel { Layout.fillWidth: true; findings: [] }
        RowLayout {
            objectName: "normalActions"
            Layout.fillWidth: true
            visible: !root.driftMode
            Text { Layout.fillWidth: true; text: root.busy ? "Applying keybinding plan…" : "Changes are saved only after review."; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.caption }
            Ui.Button { text: "Reset draft"; focusable: true; enabled: !root.busy; onClicked: root.requestReset() }
            Ui.Button { objectName: "reviewButton"; text: "Review changes"; focusable: true; enabled: root.editCapability.available && !root.busy; onClicked: root.requestPlan() }
            Ui.Button { objectName: "applyButton"; text: "Apply"; focusable: true; enabled: root.editCapability.available && !root.busy; onClicked: root.requestApply() }
        }
    }

    ChordCapture {
        id: capture
        anchors.fill: parent
        z: 10
        onCaptured: function(value) { chord.setValueAndNormalize(value.sourceKeys) }
        onRefused: function(reason) { root.stateMessage = reason }
    }
}
