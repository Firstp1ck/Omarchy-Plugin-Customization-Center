import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui
import "." as Components

FocusScope {
    id: root
    property string moduleId: "monitors"
    property var status: null
    property var capabilities: ({})
    property var draft: ({})
    property bool busy: false
    property var backendClient: null
    property string selectedProfileId: draft && draft.profileId ? draft.profileId : ""
    property string selectedOutputId: ""
    property var preview: ({ schemaVersion: 1, rectangles: [], bounds: ({ x: 0, y: 0, width: 0, height: 0 }) })
    property var lastPayload: null
    readonly property var statusData: status && status.data ? status.data : status
    readonly property var profiles: statusData && statusData.profiles ? statusData.profiles : []

    signal requestPlan()
    signal requestApply()
    signal requestReset()
    signal requestDraftPatch(var patch)
    signal requestNavigate(string moduleId, var payload)

    function emitPatch(patch) {
        requestDraftPatch(patch)
    }
    function focusFirst() {
        profileList.forceActiveFocus()
    }
    function handlePayload(payload) {
        lastPayload = payload
        if (payload && payload.profileId) selectProfile(payload.profileId)
    }
    function profileById(profileId) {
        for (var i = 0; i < profiles.length; ++i)
            if (profiles[i].id === profileId) return profiles[i]
        return null
    }
    function selectProfile(profileId) {
        selectedProfileId = profileId
        var row = profileById(profileId)
        emitPatch({ schemaVersion: 1, action: "activate", profileId: profileId, profile: row && row.profile ? row.profile : null })
        if (!row || !row.profile) return
        if (backendClient) {
            backendClient.query(moduleId, "layout-preview", { profile: row.profile }, function(result) {
                if (result && result.ok) root.preview = result.data
            })
        }
    }
    function editableProfile() {
        if (draft && draft.profile) return JSON.parse(JSON.stringify(draft.profile))
        var row = profileById(selectedProfileId)
        return row && row.profile ? JSON.parse(JSON.stringify(row.profile)) : null
    }
    function selectedRule() {
        var value = editableProfile()
        if (!value) return null
        for (var i = 0; i < value.outputs.length; ++i)
            if (value.outputs[i].id === selectedOutputId) return value.outputs[i]
        return null
    }
    function selectedInventory() {
        var rule = selectedRule()
        var outputs = statusData && statusData.inventory ? statusData.inventory.outputs : []
        if (!rule) return null
        var connector = draft && draft.assignments && draft.assignments[rule.id] ? draft.assignments[rule.id] : rule.identity.connector
        for (var i = 0; i < outputs.length; ++i) if (outputs[i].connector === connector) return outputs[i]
        var cached = statusData && statusData.cachedModes ? statusData.cachedModes : []
        for (var j = 0; j < cached.length; ++j)
            if (cached[j].profileId === selectedProfileId && cached[j].outputId === rule.id)
                return { modes: cached[j].modes, stale: true, observedAt: cached[j].observedAt }
        return null
    }
    function validScale120(rule, scale120) {
        if (!rule || scale120 < 30 || scale120 > 960) return false
        var width = rule.mode.width
        var height = rule.mode.height
        if ([1, 3, 5, 7].indexOf(rule.transform) >= 0) { var swap = width; width = height; height = swap }
        return (width * 120) % scale120 === 0 && (height * 120) % scale120 === 0
    }
    function setScale120(scale120) {
        var rule = selectedRule()
        scaleState.text = validScale120(rule, scale120) ? "" : "Scale must produce integral logical pixels"
        if (scaleState.text === "") patchOutput(selectedOutputId, { scale120: scale120 })
    }
    function mirrorOptions() {
        var value = editableProfile(); var options = [{ value: "", label: "Not mirrored" }]
        if (!value) return options
        for (var i = 0; i < value.outputs.length; ++i) {
            var item = value.outputs[i]
            if (item.id !== selectedOutputId && item.enabled && !item.mirrorOf) options.push({ value: item.id, label: item.label })
        }
        return options
    }
    function mirrorToFirstRoot() {
        var value = editableProfile()
        if (!value) return
        for (var i = 0; i < value.outputs.length; ++i)
            if (value.outputs[i].id !== selectedOutputId && value.outputs[i].enabled && !value.outputs[i].mirrorOf)
                return patchOutput(selectedOutputId, { mirrorOf: value.outputs[i].id })
    }
    function patchOutput(outputId, changes) {
        var value = editableProfile()
        if (!value) return
        for (var i = 0; i < value.outputs.length; ++i) {
            if (value.outputs[i].id !== outputId) continue
            for (var key in changes) {
                if (key === "position") value.outputs[i].position = Object.assign({}, value.outputs[i].position, changes.position)
                else value.outputs[i][key] = changes[key]
            }
            emitPatch({ profile: value })
            return
        }
    }
    function nudgeOutput(outputId, dx, dy) {
        var value = editableProfile()
        if (!value) return
        for (var i = 0; i < value.outputs.length; ++i)
            if (value.outputs[i].id === outputId)
                return patchOutput(outputId, { position: { x: value.outputs[i].position.x + dx, y: value.outputs[i].position.y + dy } })
    }
    function duplicateSelectedProfile() {
        var value = editableProfile()
        if (!value) return
        value.id = value.id + "-copy"
        value.name = value.name + " copy"
        value.updatedAt = new Date().toISOString()
        emitPatch({ schemaVersion: 1, action: "save-profile", profile: value, profileId: null })
    }
    function renameSelectedProfile() {
        var value = editableProfile()
        if (!value) return
        value.name = value.name + " renamed"
        value.updatedAt = new Date().toISOString()
        emitPatch({ schemaVersion: 1, action: "save-profile", profile: value })
    }
    function deleteSelectedProfile() {
        if (selectedProfileId) emitPatch({ schemaVersion: 1, action: "delete-profile", profileId: selectedProfileId, profile: null })
    }
    function assignOutput(outputId, connector) {
        var assignments = Object.assign({}, draft && draft.assignments ? draft.assignments : {})
        assignments[outputId] = connector
        emitPatch({ assignments: assignments })
    }
    function createFromCurrent(templateName) {
        var template = templateName || "capture"
        var outputs = statusData && statusData.inventory ? statusData.inventory.outputs : []
        if (!outputs.length) return
        var now = new Date().toISOString()
        var rules = outputs.map(function(item, index) {
            return { id: "output-" + (index + 1), label: item.make + " " + item.model,
                identity: { description: item.description, make: item.make, model: item.model, serial: item.serial, connector: item.connector },
                connectorPolicy: "confirm", enabled: !item.disabled,
                mode: { width: Math.max(1, item.width), height: Math.max(1, item.height), refreshMilliHz: Math.max(1, item.refreshMilliHz) },
                position: { x: item.x, y: item.y }, scale120: item.scale120, transform: item.transform,
                mirrorOf: null, bitDepth: null, vrr: null, whenMissing: "block" }
        })
        if (template === "laptop") {
            for (var laptopIndex = 0; laptopIndex < rules.length; ++laptopIndex) rules[laptopIndex].enabled = outputs[laptopIndex].internal
        } else if (template === "extend") {
            var nextX = 0
            for (var extendIndex = 0; extendIndex < rules.length; ++extendIndex) { rules[extendIndex].position.x = nextX; nextX += Math.round(rules[extendIndex].mode.width * 120 / rules[extendIndex].scale120) }
        } else if (template === "mirror" && rules.length > 1) {
            for (var mirrorIndex = 1; mirrorIndex < rules.length; ++mirrorIndex) rules[mirrorIndex].mirrorOf = rules[0].id
        }
        var value = { schemaVersion: 1, id: template === "capture" ? "current-layout" : template + "-layout", name: template === "capture" ? "Current layout" : template + " template", description: "Created from connected outputs",
            outputs: rules, match: { required: rules.map(function(item) { return item.id }), allowExtra: false },
            extraOutputs: null, createdAt: now, updatedAt: now }
        selectedProfileId = value.id
        emitPatch({ schemaVersion: 1, action: "save-profile", profile: value })
    }

    Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight + Style.spacing.panelPadding * 2
        clip: true

        ColumnLayout {
            id: content
            x: Style.spacing.panelPadding
            y: Style.spacing.panelPadding
            width: parent.width - Style.spacing.panelPadding * 2
            spacing: Style.spacing.panelGap

            RowLayout {
                Layout.fillWidth: true
                ColumnLayout {
                    Layout.fillWidth: true
                    Text { text: "Monitor layout profiles"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading; font.bold: true }
                    Text {
                        Layout.fillWidth: true
                        text: statusData && statusData.active ? ("Active: " + (statusData.active.profileId || "none") + " · " + statusData.active.state + " · GDK_SCALE " + (statusData.related.gdkScale === null ? "unknown" : statusData.related.gdkScale) + ", monitor scale " + statusData.related.monitorScaleLocal + " from ~/.config/hypr/monitors.lua") : "Loading ~/.config/hypr/monitors.lua and the active monitor setting. Wait, then retry if this does not finish."
                        color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall; wrapMode: Text.WordWrap
                    }
                }
                Ui.Button { text: "Refresh"; bordered: true; focusable: true; enabled: !root.busy; onClicked: root.requestPlan() }
            }

            Components.OverrideBanner {
                Layout.fillWidth: true
                visible: !statusData
                title: "Loading monitor configuration"
                fileName: "~/.config/hypr/monitors.lua"
                setting: "hyprctl monitors all"
                recoveryAction: "Wait for inventory, then use Refresh"
                onActionRequested: root.requestPlan()
            }
            Components.OverrideBanner {
                Layout.fillWidth: true
                visible: statusData && statusData.inventory && statusData.inventory.error
                title: "Monitor inventory is unavailable"
                fileName: "hyprctl monitors all"
                setting: statusData && statusData.inventory && statusData.inventory.error ? statusData.inventory.error.message : "runtime unavailable"
                recoveryAction: "Run inside a Hyprland session, then Refresh. Profile editing remains available."
                onActionRequested: root.requestPlan()
            }
            Components.OverrideBanner {
                Layout.fillWidth: true
                visible: statusData && statusData.loader && ["duplicate", "unterminated", "reversed", "nested"].indexOf(statusData.loader.state) >= 0
                title: "Unsupported monitor loader markers"
                fileName: "~/.config/hypr/monitors.lua"
                setting: "MONITORS v1 managed block is " + (statusData && statusData.loader ? statusData.loader.state : "invalid")
                recoveryAction: "Open the file, keep one complete marker pair, then Refresh"
                onActionRequested: root.requestPlan()
            }
            Components.OverrideBanner {
                Layout.fillWidth: true
                visible: statusData && statusData.handwritten && statusData.handwritten.conflicts && statusData.handwritten.conflicts.length > 0
                title: "Handwritten monitor rule conflicts"
                fileName: "~/.config/hypr/monitors.lua"
                setting: "hl.monitor at line " + (statusData && statusData.handwritten && statusData.handwritten.conflicts.length ? statusData.handwritten.conflicts[0].line : "unknown")
                recoveryAction: "Remove or comment the conflicting call in Setup > Monitors, then Refresh"
                onActionRequested: root.requestPlan()
            }
            Components.OverrideBanner {
                Layout.fillWidth: true
                visible: statusData && statusData.capabilities && !statusData.capabilities.apply && !(statusData.inventory && statusData.inventory.error)
                title: "Safe apply is unavailable"
                fileName: "$XDG_RUNTIME_DIR and systemd-run --user"
                setting: "timed_confirmation"
                recoveryAction: "Restore the user systemd manager and Hyprland environment. Save profiles only until then."
                actionLabel: "Check again"
                onActionRequested: root.requestPlan()
            }
            Components.OverrideBanner {
                Layout.fillWidth: true
                visible: statusData && statusData.active && ["rollback_failed", "recovery_required"].indexOf(statusData.active.state) >= 0
                title: "Monitor recovery is required"
                fileName: "~/.local/state/omarchy/customization-center/transactions/"
                setting: "rollback state"
                recoveryAction: "Restore the named backup file, resolve the transaction, then Refresh"
                onActionRequested: root.requestNavigate("history", { moduleId: root.moduleId })
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Style.spacing.panelGap
                ColumnLayout {
                    Layout.preferredWidth: Style.space(230)
                    Components.ProfileList {
                        id: profileList
                        Layout.fillWidth: true
                        profiles: root.profiles
                        selectedId: root.selectedProfileId
                        onSelected: function(profileId) { root.selectProfile(profileId) }
                    }
                    Ui.Button { objectName: "captureCurrentButton"; text: "Capture current"; bordered: true; focusable: true; enabled: statusData && statusData.inventory && statusData.inventory.outputs.length > 0; onClicked: root.createFromCurrent("capture") }
                    RowLayout {
                        Ui.Button { text: "Laptop template"; bordered: true; focusable: true; enabled: statusData && statusData.inventory && statusData.inventory.outputs.length > 0; onClicked: root.createFromCurrent("laptop") }
                        Ui.Button { text: "Extend template"; bordered: true; focusable: true; enabled: statusData && statusData.inventory && statusData.inventory.outputs.length > 0; onClicked: root.createFromCurrent("extend") }
                        Ui.Button { text: "Mirror template"; bordered: true; focusable: true; enabled: statusData && statusData.inventory && statusData.inventory.outputs.length > 1; onClicked: root.createFromCurrent("mirror") }
                    }
                    RowLayout {
                        Ui.Button { text: "Duplicate"; bordered: true; focusable: true; enabled: root.selectedProfileId !== ""; onClicked: root.duplicateSelectedProfile() }
                        Ui.Button { text: "Rename"; bordered: true; focusable: true; enabled: root.selectedProfileId !== ""; onClicked: root.renameSelectedProfile() }
                        Ui.Button { text: "Delete"; bordered: true; focusable: true; enabled: root.selectedProfileId !== ""; onClicked: root.deleteSelectedProfile() }
                    }
                }
                Components.LayoutCanvas {
                    objectName: "layoutCanvas"
                    Layout.fillWidth: true
                    preview: root.preview
                    selectedId: root.selectedOutputId
                    onSelected: function(outputId) { root.selectedOutputId = outputId }
                    onMoveRequested: function(outputId, dx, dy) { root.nudgeOutput(outputId, dx, dy) }
                }
                Ui.BorderSurface {
                    Layout.preferredWidth: Style.space(260)
                    Layout.minimumHeight: Style.space(320)
                    color: Color.popups.background
                    borderSpec: Border.controlSpec("normal", Color.foreground, Color.accent)
                    ColumnLayout {
                        anchors.fill: parent; anchors.margins: Style.spacing.rowPaddingX; spacing: Style.spacing.md
                        Text { text: "Output inspector"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; font.bold: true }
                        Text { Layout.fillWidth: true; text: root.selectedOutputId ? (root.selectedOutputId + " · position, mode, scale120, transform, mirror, bit depth, VRR and whenMissing settings") : "Select an output in the canvas. The profile JSON file is changed only through a draft patch."; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall; wrapMode: Text.WordWrap }
                        RowLayout {
                            Text { text: "X"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.caption }
                            Ui.NumberField {
                                objectName: "positionXField"
                                from: -32768; to: 32768
                                value: { var rule = root.selectedRule(); return rule ? rule.position.x : 0 }
                                onModified: function(value) { root.patchOutput(root.selectedOutputId, { position: { x: value } }) }
                            }
                            Text { text: "Y"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.caption }
                            Ui.NumberField {
                                objectName: "positionYField"
                                from: -32768; to: 32768
                                value: { var rule = root.selectedRule(); return rule ? rule.position.y : 0 }
                                onModified: function(value) { root.patchOutput(root.selectedOutputId, { position: { y: value } }) }
                            }
                        }
                        Components.ModePicker {
                            objectName: "modePicker"
                            Layout.fillWidth: true
                            modes: { var output = root.selectedInventory(); return output ? output.modes : [] }
                            stale: { var output = root.selectedInventory(); return output ? output.stale === true : false }
                            value: { var rule = root.selectedRule(); return rule ? rule.mode : null }
                            onModeSelected: function(mode) { root.patchOutput(root.selectedOutputId, { mode: mode }) }
                        }
                        Text { text: "Scale ×120"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.caption }
                        Ui.NumberField {
                            objectName: "scaleField"
                            from: 30; to: 960
                            value: { var rule = root.selectedRule(); return rule ? rule.scale120 : 120 }
                            onModified: function(value) { root.setScale120(value) }
                        }
                        Text { id: scaleState; Layout.fillWidth: true; text: ""; visible: text !== ""; color: Color.urgent; font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap }
                        Ui.Dropdown {
                            objectName: "transformPicker"
                            value: { var rule = root.selectedRule(); return rule ? String(rule.transform) : "0" }
                            options: [
                                { value: "0", label: "Normal" }, { value: "1", label: "90°" }, { value: "2", label: "180°" }, { value: "3", label: "270°" },
                                { value: "4", label: "Flipped" }, { value: "5", label: "Flipped 90°" }, { value: "6", label: "Flipped 180°" }, { value: "7", label: "Flipped 270°" }
                            ]
                            onChanged: function(value) { root.patchOutput(root.selectedOutputId, { transform: Number(value) }) }
                        }
                        Ui.Dropdown {
                            objectName: "mirrorPicker"
                            value: { var rule = root.selectedRule(); return rule && rule.mirrorOf ? rule.mirrorOf : "" }
                            options: root.mirrorOptions()
                            onChanged: function(value) { root.patchOutput(root.selectedOutputId, { mirrorOf: value === "" ? null : value }) }
                        }
                        Ui.Button { text: "Nudge right 8 px"; bordered: true; focusable: true; enabled: root.selectedOutputId !== ""; onClicked: root.nudgeOutput(root.selectedOutputId, 8, 0) }
                        RowLayout {
                            Ui.Button { text: "Scale 1"; bordered: true; focusable: true; enabled: root.selectedOutputId !== ""; onClicked: root.patchOutput(root.selectedOutputId, { scale120: 120 }) }
                            Ui.Button { text: "Scale 1.5"; bordered: true; focusable: true; enabled: root.selectedOutputId !== ""; onClicked: root.patchOutput(root.selectedOutputId, { scale120: 180 }) }
                        }
                        RowLayout {
                            Ui.Button { text: "Rotate 0°"; bordered: true; focusable: true; enabled: root.selectedOutputId !== ""; onClicked: root.patchOutput(root.selectedOutputId, { transform: 0 }) }
                            Ui.Button { text: "Rotate 90°"; bordered: true; focusable: true; enabled: root.selectedOutputId !== ""; onClicked: root.patchOutput(root.selectedOutputId, { transform: 1 }) }
                        }
                        RowLayout {
                            Ui.Button { text: "Mirror first root"; bordered: true; focusable: true; enabled: root.selectedOutputId !== ""; onClicked: root.mirrorToFirstRoot() }
                            Ui.Button { text: "No mirror"; bordered: true; focusable: true; enabled: root.selectedOutputId !== ""; onClicked: root.patchOutput(root.selectedOutputId, { mirrorOf: null }) }
                        }
                        Ui.Button { text: "Use first reported mode"; bordered: true; focusable: true; enabled: root.selectedOutputId !== "" && statusData && statusData.inventory && statusData.inventory.outputs.length > 0 && statusData.inventory.outputs[0].modes.length > 0; onClicked: root.patchOutput(root.selectedOutputId, { mode: statusData.inventory.outputs[0].modes[0] }) }
                        RowLayout {
                            Ui.Button { text: "Enabled"; bordered: true; focusable: true; enabled: root.selectedOutputId !== ""; onClicked: root.patchOutput(root.selectedOutputId, { enabled: true }) }
                            Ui.Button { text: "Disabled"; bordered: true; focusable: true; enabled: root.selectedOutputId !== ""; onClicked: root.patchOutput(root.selectedOutputId, { enabled: false }) }
                        }
                        RowLayout {
                            Ui.Button { text: "Bit depth default"; bordered: true; focusable: true; enabled: root.selectedOutputId !== ""; onClicked: root.patchOutput(root.selectedOutputId, { bitDepth: null }) }
                            Ui.Button { text: "10-bit"; bordered: true; focusable: true; enabled: root.selectedOutputId !== ""; onClicked: root.patchOutput(root.selectedOutputId, { bitDepth: 10 }) }
                        }
                        RowLayout {
                            Ui.Button { text: "VRR default"; bordered: true; focusable: true; enabled: root.selectedOutputId !== ""; onClicked: root.patchOutput(root.selectedOutputId, { vrr: null }) }
                            Ui.Button { text: "VRR on"; bordered: true; focusable: true; enabled: root.selectedOutputId !== ""; onClicked: root.patchOutput(root.selectedOutputId, { vrr: 1 }) }
                        }
                        RowLayout {
                            Ui.Button { text: "Missing blocks"; bordered: true; focusable: true; enabled: root.selectedOutputId !== ""; onClicked: root.patchOutput(root.selectedOutputId, { whenMissing: "block" }) }
                            Ui.Button { text: "Missing skips"; bordered: true; focusable: true; enabled: root.selectedOutputId !== ""; onClicked: root.patchOutput(root.selectedOutputId, { whenMissing: "skip" }) }
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                visible: {
                    var row = root.profileById(root.selectedProfileId)
                    return row && row.fit && row.fit.ambiguous && row.fit.ambiguous.length > 0
                }
                Text { text: "Ambiguous output assignment"; color: Color.urgent; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; font.bold: true }
                Repeater {
                    model: {
                        var row = root.profileById(root.selectedProfileId)
                        return row && row.fit ? row.fit.ambiguous : []
                    }
                    delegate: RowLayout {
                        required property var modelData
                        Text { text: modelData.outputId; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body }
                        Repeater {
                            id: candidateRepeater
                            property string outputId: parent.modelData.outputId
                            model: parent.modelData.candidates
                            delegate: Ui.Button {
                                required property var modelData
                                text: modelData; bordered: true; focusable: true
                                onClicked: root.assignOutput(candidateRepeater.outputId, modelData)
                            }
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                visible: !!(status && status.warnings && status.warnings.length > 0)
                Text { text: "Warnings"; color: Color.urgent; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; font.bold: true }
                Repeater {
                    model: status && status.warnings ? status.warnings : []
                    delegate: Text { required property var modelData; Layout.fillWidth: true; text: modelData.code + ": " + modelData.message + " · " + (modelData.recovery || "Review before applying"); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall; wrapMode: Text.WordWrap }
                }
            }

            Components.OverrideBanner {
                Layout.fillWidth: true
                visible: statusData && statusData.active && statusData.active.state === "awaiting-confirmation"
                title: "Awaiting monitor confirmation"
                fileName: "~/.local/state/omarchy/customization-center/transactions/"
                setting: "TimedConfirmation(30)"
                recoveryAction: "Use the confirmation dialog on any output or wait for automatic rollback"
                actionLabel: "Transaction history"
                onActionRequested: root.requestNavigate("history", { moduleId: root.moduleId })
            }
            Components.OverrideBanner {
                Layout.fillWidth: true
                visible: statusData && statusData.active && statusData.active.state === "drifted"
                title: "Active monitor profile drifted"
                fileName: "generated/monitors.lua and active.json"
                setting: "profile topology"
                recoveryAction: "Review and reapply the profile, or update it from the current layout"
                actionLabel: "Review"
                onActionRequested: root.requestPlan()
            }

            Text {
                Layout.fillWidth: true
                visible: root.profiles.length === 0
                text: "Empty profile store: ~/.config/omarchy/customization-center/monitor-profiles/ contains no layout. Use New from current to create the monitor profile setting."
                color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.body; wrapMode: Text.WordWrap
            }

            Ui.BorderSurface {
                Layout.fillWidth: true
                color: Color.popups.background
                borderSpec: Border.controlSpec("normal", Color.foreground, Color.accent)
                implicitHeight: actions.implicitHeight + Style.spacing.rowPaddingX * 2
                RowLayout {
                    id: actions; anchors.fill: parent; anchors.margins: Style.spacing.rowPaddingX; spacing: Style.spacing.md
                    Text { Layout.fillWidth: true; text: root.busy ? "Applying monitor layout. Confirmation appears on every output." : "Review generated/monitors.lua and ~/.config/hypr/monitors.lua before apply."; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; wrapMode: Text.WordWrap }
                    Ui.Button { text: "Reset draft"; bordered: true; focusable: true; enabled: !root.busy; onClicked: root.requestReset() }
                    Ui.Button { text: "Review changes"; bordered: true; focusable: true; enabled: !root.busy && root.selectedProfileId !== ""; onClicked: root.requestPlan() }
                    Ui.Button { text: "Apply and confirm within 30 s"; bordered: true; focusable: true; enabled: !root.busy && root.selectedProfileId !== "" && statusData && statusData.capabilities && statusData.capabilities.apply; onClicked: root.requestApply() }
                }
            }
        }
    }
}
