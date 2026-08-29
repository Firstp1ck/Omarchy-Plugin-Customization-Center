import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui
import "." as Menu

FocusScope {
    id: root
    property string moduleId: "menu"
    property var status: null
    property var capabilities: ({})
    property var draft: ({})
    property bool busy: false
    property var backendClient: null
    property string selectedId: ""
    property var projectedEffective: statusData.effective || ({ order: [], rows: ({}) })
    property string pendingDeleteId: ""
    property string deleteConfirmationText: ""
    property bool deletePromptVisible: false
    property string acceptedDuplicateRevision: ""
    readonly property bool reviewEnabled: !shellUnavailable && !busy && !recoveryState
    readonly property bool editorVisible: !recoveryState && !busy && status !== null
    readonly property bool recoveryVisible: recoveryState && !busy
    readonly property alias deleteDialog: deleteConfirm
    objectName: "menuPageContent"

    signal requestPlan()
    signal requestApply()
    signal requestReset()
    signal requestDraftPatch(var patch)
    signal requestNavigate(string moduleId, var payload)

    readonly property var statusData: status && status.data ? status.data : ({})
    readonly property var effective: projectedEffective || statusData.effective || ({ order: [], rows: ({}) })
    readonly property string documentState: statusData.documentState || "loading"
    readonly property string menuPath: statusData.user && statusData.user.path ? statusData.user.path : "~/.config/omarchy/extensions/omarchy-menu.jsonc"
    readonly property bool recoveryState: ["malformed", "hazard", "unsupported"].indexOf(documentState) >= 0
        || (documentState === "duplicate-keys" && acceptedDuplicateRevision !== (status ? status.revision : ""))
    readonly property var selectedRow: selectedId && effective.rows ? effective.rows[selectedId] : null
    readonly property bool shellUnavailable: {
        var items = capabilities && capabilities.items ? capabilities.items : []
        for (var i = 0; i < items.length; ++i)
            if (items[i].name === "shell") return items[i].available !== true
        return true
    }
    readonly property string shellUnavailableReason: {
        var items = capabilities && capabilities.items ? capabilities.items : []
        for (var i = 0; i < items.length; ++i)
            if (items[i].name === "shell") return items[i].reason || "omarchy-menu ping failed"
        return "Shell capability was not reported"
    }
    readonly property var selectedDraftEntry: {
        var entries = draft && draft.entries ? draft.entries : []
        for (var i = 0; i < entries.length; ++i)
            if (entries[i].id === selectedId) return entries[i]
        return null
    }

    function emitPatch(patch) {
        requestDraftPatch(patch)
    }
    function refreshProjection() {
        var current = root.draft
        if (!current || current.schemaVersion !== 1 || !backendClient) {
            projectedEffective = statusData.effective || ({ order: [], rows: ({}) })
            return
        }
        backendClient.query(moduleId, "projection", ({ draft: current }), function(result) {
            var data = result && result.data ? result.data : null
            if (data && data.effective)
                projectedEffective = data.effective
        })
    }
    function baseDraft() {
        var entries = []
        var document = statusData.document
        var source = document && document.entries ? document.entries : []
        for (var i = 0; i < source.length; ++i) {
            var item = source[i]
            var fields = ({})
            var passthrough = ({})
            var knownEditable = ["icon", "iconFont", "label", "title", "description", "action", "target", "provider", "when", "checked", "disabled"]
            var rawFields = item.fields || ({})
            for (var key in rawFields) {
                if (knownEditable.indexOf(key) >= 0) fields[key] = rawFields[key]
                else passthrough[key] = rawFields[key]
            }
            var kind = fields.action ? "command" : fields.target ? "link" : fields.provider ? "provider" : "submenu"
            entries.push({ draftId: "existing-" + i, id: item.id, originalId: item.id,
                           origin: item.valueKind === "other" || (item.typeErrors && item.typeErrors.length) ? "preserved" : (effective.rows[item.id] && effective.rows[item.id].origin === "shadowed" ? "shadowed" : "custom"),
                           kind: kind, fields: fields, passthrough: passthrough,
                           raw: item.valueKind === "other" ? item.raw : null, deleted: false })
        }
        return { schemaVersion: 1, module: "menu", baseRevision: status ? status.revision : statusData.revision || "",
                 semantics: statusData.overrideSemantics || "full-shadow", shape: document ? document.shape : "direct", bom: false,
                 entries: entries, wrapperSiblings: document ? document.wrapperSiblings || [] : [], recovery: null }
    }
    function currentDraft() {
        var current = root.draft
        return current && current.schemaVersion === 1 ? current : baseDraft()
    }
    function replaceEntries(entries) {
        var next = currentDraft()
        var patch = Object.assign({}, next)
        patch.entries = entries
        emitPatch(patch)
    }
    function addEntry() {
        var next = currentDraft()
        var entries = (next.entries || []).slice()
        var id = "personal.new-item"
        var suffix = 2
        while (entries.some(function(row) { return row.id === id })) id = "personal.new-item-" + suffix++
        entries.push({ draftId: "new-" + Date.now(), id: id, originalId: null, origin: "custom", kind: "command",
                       fields: ({ label: "New item", action: "true" }), passthrough: ({}), raw: null, deleted: false })
        replaceEntries(entries)
        selectedId = id
    }
    function editSelected(field, value) {
        var next = currentDraft()
        var entries = (next.entries || []).map(function(entry) {
            if (entry.id !== selectedId) return entry
            var copy = Object.assign({}, entry)
            var fields = Object.assign({}, entry.fields || ({}))
            if (value === "") delete fields[field]
            else fields[field] = value
            copy.fields = fields
            return copy
        })
        replaceEntries(entries)
    }
    function renameSelected(value) {
        var entries = (currentDraft().entries || []).map(function(entry) {
            if (entry.id !== selectedId) return entry
            var copy = Object.assign({}, entry)
            copy.id = value
            return copy
        })
        selectedId = value
        replaceEntries(entries)
    }
    function requestDeleteSelected() {
        if (!selectedId) return
        pendingDeleteId = selectedId
        deleteConfirmationText = ""
        deletePromptVisible = true
    }
    function openDeleteDialog() {
        if (deleteConfirmationText !== pendingDeleteId) return
        deletePromptVisible = false
        deleteConfirm.message = "Delete or remove the shadow for “" + pendingDeleteId + "”? The typed entry id matched."
        deleteConfirm.opened = true
    }
    function cancelDelete() {
        deleteConfirm.opened = false
        deletePromptVisible = false
        pendingDeleteId = ""
        deleteConfirmationText = ""
    }
    function confirmDelete() {
        var deleteId = pendingDeleteId
        if (!deleteId || deleteConfirmationText !== deleteId) return
        deleteConfirm.opened = false
        deletePromptVisible = false
        pendingDeleteId = ""
        deleteConfirmationText = ""
        var entries = (currentDraft().entries || []).map(function(entry) {
            if (entry.id !== deleteId) return entry
            var copy = Object.assign({}, entry)
            copy.deleted = true
            return copy
        })
        replaceEntries(entries)
    }
    function beginRecovery() {
        var next = baseDraft()
        if (documentState === "duplicate-keys") {
            acceptedDuplicateRevision = status ? status.revision : ""
            emitPatch(next)
            return
        }
        next.entries = []
        next.recovery = ({ mode: "replace-after-backup", backupOfRevision: status ? status.revision : statusData.revision || "" })
        emitPatch(next)
        requestPlan()
    }
    function focusFirst() {
        if (recoveryState) recovery.focusFirst()
        else tree.focusFirst()
    }
    function handlePayload(payload) {
        if (!payload) return
        if (typeof payload.select === "string") tree.selectId(payload.select)
        if (typeof payload.route === "string" && backendClient)
            backendClient.query(moduleId, "route", ({ input: payload.route, draft: root.draft }), function(result) {
                if (result && result.data && result.data.resolved) tree.selectId(result.data.resolved)
            })
    }

    onDraftChanged: refreshProjection()
    onStatusChanged: refreshProjection()
    onBackendClientChanged: refreshProjection()

    ColumnLayout {
        anchors.fill: parent
        spacing: Style.spacing.md

        Ui.BorderSurface {
            Layout.fillWidth: true
            implicitHeight: bannerText.implicitHeight + Style.spacing.md * 2
            color: documentState === "unsupported" || documentState === "malformed" ? Style.normalFillFor(Color.urgent, Color.accent, Color.urgent) : Style.normalFill
            borderSpec: Border.controlSpec("normal", documentState === "unsupported" ? Color.urgent : Color.foreground, Color.accent, Color.urgent)
            Text {
                id: bannerText
                anchors.fill: parent
                anchors.margins: Style.spacing.md
                text: busy ? "Loading personal menu setting from " + menuPath : root.shellUnavailable ? "Personal menu setting in " + menuPath + " cannot be applied: " + root.shellUnavailableReason + ". Start or enable omarchy.menu, then retry Apply." : documentState === "empty" || documentState === "absent" ? "No personal entries in " + menuPath + ". Add an entry, then Review and Apply." : "Personal menu file: " + menuPath + " · Override semantics: " + (statusData.overrideSemantics || "full-shadow")
                color: Color.foreground
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
            }
        }

        Ui.BorderSurface {
            objectName: "loadingPresentation"
            Layout.fillWidth: true
            implicitHeight: loadingText.implicitHeight + Style.spacing.md * 2
            visible: busy || !status
            color: Style.normalFill
            borderSpec: Border.controlSpec("normal", Color.foreground, Color.accent)
            Text {
                id: loadingText
                anchors.centerIn: parent
                text: "Loading " + root.menuPath + " for the personal menu setting. Wait, then retry Reload if it does not finish."
                color: Color.muted
                font.family: Style.font.family
                font.pixelSize: Style.font.body
            }
        }

        RowLayout {
            Layout.alignment: Qt.AlignRight
            visible: !root.busy && root.status
            Ui.Button {
                id: reviewButton
                objectName: "menuReviewButton"
                text: "Review"
                bordered: true
                focusable: true
                enabled: root.reviewEnabled
                onClicked: root.requestPlan()
            }
            Ui.Button {
                id: applyButton
                objectName: "menuApplyButton"
                text: "Apply"
                bordered: true
                focusable: true
                enabled: root.reviewEnabled
                onClicked: root.requestApply()
            }
        }

        Menu.RecoveryPanel {
            id: recovery
            objectName: "menuRecoveryPanel"
            Layout.fillWidth: true
            visible: root.recoveryVisible
            filePath: root.menuPath
            state: root.documentState
            detail: root.documentState === "hazard" ? "The shell parser alters a setting in this file." : root.documentState === "duplicate-keys" ? "Duplicate settings keep only their last occurrence." : root.documentState === "unsupported" ? "The path or shipped menu format is unsupported." : "The shell currently loads no personal entries from this malformed file."
            onReplaceRequested: root.beginRecovery()
            onReloadRequested: root.requestReset()
        }

        RowLayout {
            id: editorLayout
            objectName: "menuEditor"
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.editorVisible
            spacing: Style.spacing.md

            ColumnLayout {
                Layout.preferredWidth: parent.width * 0.48
                Layout.fillHeight: true
                spacing: Style.spacing.md
                RowLayout {
                    Layout.fillWidth: true
                    Ui.TextField { id: filterField; Layout.fillWidth: true; placeholderText: "Filter personal menu settings"; onTextEdited: tree.filterText = text }
                    Ui.Button { text: "Add"; bordered: true; focusable: true; onClicked: root.addEntry() }
                }
                Menu.MenuTree {
                    id: tree
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    effective: root.effective
                    selectedId: root.selectedId
                    onSelected: entryId => root.selectedId = entryId
                    onEditRequested: inspector.focusFirst()
                }
            }
            Ui.BorderSurface {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: Style.normalFill
                borderSpec: Border.controlSpec("normal", Color.foreground, Color.accent)
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Style.spacing.lg
                    spacing: Style.spacing.lg
                    Menu.EntryInspector {
                        id: inspector
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        row: root.selectedRow
                        draftEntry: root.selectedDraftEntry
                        onFieldEdited: (field, value) => root.editSelected(field, value)
                        onIdEdited: value => root.renameSelected(value)
                        onRemoveShadowRequested: root.requestDeleteSelected()
                    }
                    Menu.RoutePreview { Layout.fillWidth: true; backendClient: root.backendClient; moduleId: root.moduleId; draft: root.draft }
                }
            }
        }
    }

    Ui.BorderSurface {
        anchors.fill: parent
        visible: root.deletePromptVisible
        color: Color.background
        borderSpec: Border.controlSpec("focus", Color.urgent, Color.accent, Color.urgent)
        z: 20
        ColumnLayout {
            anchors.centerIn: parent
            width: Math.min(parent.width - Style.spacing.panelPadding * 2, Style.space(460))
            spacing: Style.spacing.md
            Text {
                Layout.fillWidth: true
                text: "Type “" + root.pendingDeleteId + "” to confirm deletion or shadow removal."
                color: Color.foreground
                font.family: Style.font.family
                font.pixelSize: Style.font.body
                wrapMode: Text.WordWrap
            }
            Ui.TextField {
                id: deleteEntryIdField
                objectName: "menuDeleteEntryId"
                Layout.fillWidth: true
                text: root.deleteConfirmationText
                placeholderText: root.pendingDeleteId
                onTextChanged: root.deleteConfirmationText = text
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                Ui.Button { text: "Cancel"; bordered: true; focusable: true; onClicked: root.cancelDelete() }
                Ui.Button { objectName: "menuDeleteContinue"; text: "Continue"; bordered: true; focusable: true; enabled: root.deleteConfirmationText === root.pendingDeleteId; onClicked: root.openDeleteDialog() }
            }
        }
    }

    Ui.ConfirmDialog {
        id: deleteConfirm
        objectName: "menuDeleteConfirm"
        anchors.fill: parent
        message: "Confirm deletion"
        z: 21
        onCanceled: root.cancelDelete()
        onConfirmed: root.confirmDelete()
    }

    Keys.onPressed: event => {
        if (deleteConfirm.handleKey(event)) { event.accepted = true }
        else if (event.modifiers & Qt.ControlModifier && event.key === Qt.Key_N) { addEntry(); event.accepted = true }
        else if (event.modifiers & Qt.ControlModifier && event.key === Qt.Key_Enter && root.reviewEnabled) { requestPlan(); event.accepted = true }
        else if (event.key === Qt.Key_Delete && selectedDraftEntry) { requestDeleteSelected(); event.accepted = true }
        else if (event.modifiers & Qt.ControlModifier && event.key === Qt.Key_F) { filterField.forceActiveFocus(); event.accepted = true }
    }
}
