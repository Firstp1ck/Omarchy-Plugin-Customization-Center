import QtQuick
import qs.Commons
import qs.Ui as Ui

Ui.BorderSurface {
    id: root
    property var category: ({})
    property var categoryDraft: null
    property var backendClient: null
    property bool busy: false
    property var pendingChoice: null
    signal draftPatch(string categoryId, var change)
    signal requestPlan()
    signal requestApply()
    signal requestReset()

    readonly property string presentationState: busy ? "applying" : category.pending ? "pending_handoff" : category.drifted ? "unsupported_config" : categoryDraft ? "drafted" : (category.state || "loading")
    implicitHeight: content.implicitHeight + Style.spacing.lg * 2
    color: Style.normalFill
    borderSpec: Border.controlSpec(presentationState === "broken" || presentationState === "probe_error" ? "focus" : "normal", presentationState === "broken" || presentationState === "probe_error" ? Color.urgent : Color.foreground, Color.accent, Color.urgent)

    function focusFirst() { picker.focusFirst() }
    function selectChoice(item) {
        if (item.state === "missing" || item.state === "unprobed") {
            pendingChoice = item
            installDialog.message = "Install and set " + item.label + " through " + category.selector + ". " + item.installer.summary + (item.installer.needsSudo ? " Sudo may prompt." : "") + (item.installer.launchesApp ? " The application opens when installation finishes." : "") + " The setting is verified after the terminal flow."
            installDialog.opened = true
        } else {
            draftPatch(category.id, ({ choice: item.id, install: false }))
        }
    }

    Column {
        id: content
        anchors.fill: parent
        anchors.margins: Style.spacing.lg
        spacing: Style.spacing.md
        Text { text: root.category.label || "Default application"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading; font.bold: true }
        Text { width: parent.width; text: root.category.summary || "Loading default application setting"; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall; wrapMode: Text.WordWrap }
        Text {
            objectName: "statePresentation"
            width: parent.width
            text: root.presentationState === "loading" ? "Loading file " + (root.category.stateFile || "the selector-owned file") + ". Setting: " + (root.category.id || "default application") + ". Recovery: wait, then retry status."
                : root.presentationState === "unsupported_config" ? "Unsupported Omarchy catalog for " + root.category.selector + ". File: " + root.category.stateFile + ". Setting: " + root.category.id + ". Recovery: update this module or restore the matching Omarchy version."
                : root.presentationState === "probe_error" ? "Unavailable capability " + ((root.category.probeError || {}).command || root.category.selector) + ". File: " + root.category.stateFile + ". Setting: " + root.category.id + ". Recovery: " + ((root.category.probeError || {}).recovery || "repair the command and retry")
                : root.presentationState === "broken" ? "Broken setting in " + root.category.stateFile + ". Setting: " + root.category.id + ". Recovery: install and set this choice, or choose another."
                : root.presentationState === "unset" || root.presentationState === "none_resolvable" ? "Empty setting in " + root.category.stateFile + ". Setting: " + root.category.id + ". Recovery: choose an application, then Review and Apply."
                : root.presentationState === "applying" ? "Applying setting " + root.category.id + " through " + root.category.selector + ". Recovery: wait for verification; rollback restores " + root.category.stateFile + "."
                : root.presentationState === "drafted" ? "Unapplied setting for " + root.category.id + ". File: " + root.category.stateFile + ". Recovery: Review and Apply, or Clear."
                : "File: " + root.category.stateFile + " · Setting: " + root.category.id + " · Recovery: choose another value or restore the Omarchy default."
            color: root.presentationState === "probe_error" || root.presentationState === "broken" ? Color.urgent : Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }
        CurrentValue { width: parent.width; category: root.category }
        PendingHandoff {
            width: parent.width
            visible: root.presentationState === "pending_handoff"
            pending: root.category.pending
            backendClient: root.backendClient
            onRecheck: if (root.backendClient && root.category.pending) root.backendClient.reconcile(root.category.pending.transactionId)
            onAbandon: if (root.backendClient && typeof root.backendClient.abandon === "function" && root.category.pending) root.backendClient.abandon(root.category.pending.transactionId)
        }
        ChoicePicker {
            id: picker
            width: parent.width
            visible: root.presentationState !== "pending_handoff"
            enabled: !root.busy && root.presentationState !== "probe_error" && root.presentationState !== "unsupported_config"
            choices: root.category.choices || []
            selector: root.category.selector || ""
            currentChoice: root.categoryDraft ? root.categoryDraft.choice : ((root.category.current || {}).choice || "")
            onChoicePicked: function(item) { root.selectChoice(item) }
        }
        Row {
            spacing: Style.spacing.sm
            Ui.Button { text: root.category.id === "agent" ? "Set and launch" : "Review"; bordered: true; focusable: true; enabled: !!root.categoryDraft && !root.busy; onClicked: root.requestPlan() }
            Ui.Button { text: "Apply"; bordered: true; focusable: true; enabled: !!root.categoryDraft && !root.busy; onClicked: root.requestApply() }
            Ui.Button { text: "Clear"; bordered: true; focusable: true; enabled: !!root.categoryDraft && !root.busy; onClicked: root.draftPatch(root.category.id, null) }
            Ui.Button { text: "Restore default"; bordered: true; focusable: true; visible: !!root.category.default; enabled: !root.busy; onClicked: root.draftPatch(root.category.id, ({ choice: root.category.default, install: false })) }
        }
    }

    Ui.ConfirmDialog {
        id: installDialog
        anchors.fill: parent
        confirmText: "Install and set"
        onCanceled: { opened = false; root.pendingChoice = null }
        onConfirmed: {
            opened = false
            if (root.pendingChoice) root.draftPatch(root.category.id, ({ choice: root.pendingChoice.id, install: true }))
            root.pendingChoice = null
        }
    }
}
