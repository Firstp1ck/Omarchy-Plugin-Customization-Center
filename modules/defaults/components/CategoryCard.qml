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
    property bool cardDetailsOpen: false
    readonly property var outcome: category.outcome || null
    readonly property string presentationState: busy ? "applying"
        : category.pending ? "pending_handoff"
        : outcome && outcome.state ? outcome.state
        : category.drifted ? "probe_error"
        : categoryDraft ? "drafted"
        : (category.state || "loading")
    readonly property var availableActions: actionNames()

    signal draftPatch(string categoryId, var change)
    signal requestPlan()
    signal requestApply()
    signal requestReset()
    signal retry()
    signal recheck()
    signal reload()
    signal abandon()

    implicitHeight: content.implicitHeight + (Style.spacing.lg || Style.space(10)) * 2
    color: Style.normalFill
    borderSpec: Border.controlSpec(presentationState === "broken" || presentationState === "probe_error" || presentationState === "rollback_failed" ? "focus" : "normal",
                                   presentationState === "broken" || presentationState === "probe_error" || presentationState === "rollback_failed" ? Color.urgent : Color.foreground,
                                   Color.accent, Color.urgent)

    function focusFirst() {
        if (presentationState === "probe_error") retryButton.forceActiveFocus()
        else if (presentationState === "stale") reloadButton.forceActiveFocus()
        else picker.focusFirst()
    }
    function actionNames() {
        if (presentationState === "loading" || presentationState === "applying") return []
        if (presentationState === "pending_handoff") return ["Recheck", "Retry", "Stop tracking", "Details"]
        if (presentationState === "installed_not_set") return ["Set", "Details"]
        if (presentationState === "verify_failed") return ["Retry", "Recheck", "Details"]
        if (presentationState === "rollback_failed") return ["Recheck", "Details"]
        if (presentationState === "stale") return ["Reload", "Details"]
        if (presentationState === "probe_error") return ["Retry", "Details"]
        if (presentationState === "broken") return ["Repair", "Details"].concat(category.default ? ["Restore default"] : [])
        var names = ["Set", "Details"]
        if (categoryDraft) names.push("Clear")
        if (category.default) names.push("Restore default")
        return names
    }
    function selectChoice(item) {
        if (item.state === "missing" || item.state === "unprobed") {
            pendingChoice = item
            installDialog.message = "Install and set " + item.label + " through " + category.selector + ". " + item.installer.summary
                + (item.installer.needsSudo ? " Sudo may prompt." : "")
                + (item.installer.launchesApp ? " The application opens when installation finishes." : "")
                + " The install runs in an Omarchy terminal. This page verifies the setting after the terminal flow."
            installDialog.opened = true
        } else {
            draftPatch(category.id, ({ choice: item.id, install: false }))
        }
    }
    function repairCurrent() {
        var currentId = (category.current || {}).choice
        var choices = category.choices || []
        for (var i = 0; i < choices.length; ++i)
            if (choices[i].id === currentId) selectChoice(choices[i])
    }
    function recoveryText() {
        if (presentationState === "loading") return "Loading " + (category.selector || "selector") + "."
        if (presentationState === "probe_error") return "Unavailable capability " + ((category.probeError || {}).command || category.selector) + ". " + ((category.probeError || {}).message || "The setting could not be read") + ". Repair it, then Retry."
        if (presentationState === "broken") return "The current choice failed one or more checks. Repair it or choose another application."
        if (presentationState === "unset") return "No coding agent is selected."
        if (presentationState === "none_resolvable") return "xdg-terminal-exec is installed but finds no terminal. Preference: " + (((category.current || {}).raw || {}).preference || "none") + "."
        if (presentationState === "applying") return "Applying through " + category.selector + "; verification and rollback are automatic."
        if (presentationState === "drafted") return "Unapplied change. Review and Apply, or Clear it."
        if (presentationState === "pending_handoff") return "Continue in the external Omarchy terminal."
        if (presentationState === "installed_not_set") return "The application was installed, but it did not become the default. Set it without reinstalling."
        if (presentationState === "verify_failed") return "Verification failed and the previous default was restored. Inspect the failed checks, then Retry or Recheck."
        if (presentationState === "rollback_failed") return "Rollback could not restore every path. Keep the backups and use the recovery commands below."
        if (presentationState === "stale") return "The default changed outside this page. Reload current state; your intended choice remains drafted."
        if (presentationState === "unknown") return "This value is not an Omarchy choice. Choosing a listed value replaces it; rollback restores the current file."
        return "Current selector-owned state is ready."
    }

    Column {
        id: content
        anchors.fill: parent
        anchors.margins: (Style.spacing.lg || Style.space(10))
        spacing: Style.spacing.md

        Text { text: root.category.label || "Default application"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading; font.bold: true }
        Text { width: parent.width; text: root.category.summary || "Loading default application setting"; color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall; wrapMode: Text.WordWrap }
        Text {
            objectName: "statePresentation"
            width: parent.width
            text: root.recoveryText()
            color: ["probe_error", "broken", "rollback_failed"].indexOf(root.presentationState) >= 0 ? Color.urgent : Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }
        CurrentValue { width: parent.width; category: root.category; visible: root.presentationState !== "loading" }
        Column {
            width: parent.width
            visible: root.presentationState === "verify_failed" || root.presentationState === "rollback_failed"
            spacing: Style.spacing.xs
            Repeater {
                model: root.outcome && root.outcome.failedChecks ? root.outcome.failedChecks : []
                delegate: Text {
                    required property var modelData
                    width: content.width
                    text: modelData.id + ": expected " + modelData.expected + ", got " + modelData.actual
                    color: Color.urgent
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                }
            }
            Repeater {
                model: root.outcome && root.outcome.paths ? root.outcome.paths : []
                delegate: Text {
                    required property var modelData
                    width: content.width
                    text: "Retained backup for " + modelData
                    color: Color.urgent
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WrapAnywhere
                }
            }
            Repeater {
                model: root.outcome && root.outcome.recoveryCommands ? root.outcome.recoveryCommands : []
                delegate: Text {
                    required property var modelData
                    width: content.width
                    text: modelData
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WrapAnywhere
                }
            }
        }
        PendingHandoff {
            width: parent.width
            visible: root.presentationState === "pending_handoff"
            pending: root.category.pending
            backendClient: root.backendClient
            onRecheck: root.recheck()
            onRetry: root.retry()
            onAbandon: root.abandon()
        }
        Ui.BorderSurface {
            width: parent.width
            visible: root.cardDetailsOpen
            implicitHeight: cardDetails.implicitHeight + Style.spacing.md * 2
            color: Style.normalFill
            borderSpec: Border.controlSpec("normal", Color.foreground, Color.accent)
            Column {
                id: cardDetails
                anchors.fill: parent
                anchors.margins: Style.spacing.md
                spacing: Style.spacing.xs
                Text { text: "Selector: " + (root.category.selector || "unavailable"); color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall }
                Text { width: parent.width; text: "State source: " + (root.category.stateFile || "selector-owned state"); color: Color.muted; font.family: Style.font.family; font.pixelSize: Style.font.bodySmall; wrapMode: Text.WrapAnywhere }
                Repeater {
                    model: root.category.checks || []
                    delegate: Text {
                        required property var modelData
                        width: cardDetails.width
                        text: modelData.id + ": " + (modelData.ok ? "pass" : "failed") + " (expected " + modelData.expected + ", actual " + modelData.actual + ")"
                        color: modelData.ok ? Color.muted : Color.urgent
                        font.family: Style.font.family
                        font.pixelSize: Style.font.bodySmall
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
        ChoicePicker {
            id: picker
            width: parent.width
            visible: root.presentationState !== "pending_handoff" && root.presentationState !== "loading" && root.presentationState !== "applying"
            enabled: !root.busy && root.presentationState !== "probe_error" && root.presentationState !== "rollback_failed" && root.presentationState !== "stale"
            choices: root.category.choices || []
            selector: root.category.selector || ""
            currentChoice: root.categoryDraft ? root.categoryDraft.choice : ((root.category.current || {}).choice || "")
            onChoicePicked: function(item) { root.selectChoice(item) }
        }
        Flow {
            width: parent.width
            spacing: (Style.spacing.sm || Style.space(6))
            Ui.Button { id: retryButton; objectName: "retryAction"; text: "Retry"; bordered: true; focusable: true; visible: ["probe_error", "verify_failed"].indexOf(root.presentationState) >= 0; enabled: !root.busy; onClicked: root.retry() }
            Ui.Button { objectName: "recheckAction"; text: "Recheck"; bordered: true; focusable: true; visible: ["verify_failed", "rollback_failed"].indexOf(root.presentationState) >= 0; enabled: !root.busy; onClicked: root.recheck() }
            Ui.Button { id: reloadButton; objectName: "reloadAction"; text: "Reload"; bordered: true; focusable: true; visible: root.presentationState === "stale"; enabled: !root.busy; onClicked: root.reload() }
            Ui.Button {
                objectName: "setAction"
                text: root.category.id === "agent" ? "Set and launch" : (root.presentationState === "broken" ? "Repair" : "Set")
                bordered: true; focusable: true
                visible: ["loading", "applying", "pending_handoff", "probe_error", "verify_failed", "rollback_failed", "stale"].indexOf(root.presentationState) < 0
                enabled: !root.busy && (!!root.categoryDraft || root.presentationState === "installed_not_set" || root.presentationState === "broken")
                onClicked: {
                    if (root.presentationState === "installed_not_set" && root.outcome && root.outcome.choice)
                        root.draftPatch(root.category.id, ({ choice: root.outcome.choice, install: false }))
                    else if (root.presentationState === "broken")
                        root.repairCurrent()
                    else
                        root.requestPlan()
                }
            }
            Ui.Button { text: "Apply"; bordered: true; focusable: true; visible: !!root.categoryDraft; enabled: !!root.categoryDraft && !root.busy; onClicked: root.requestApply() }
            Ui.Button { text: "Clear"; bordered: true; focusable: true; visible: !!root.categoryDraft; enabled: !!root.categoryDraft && !root.busy; onClicked: root.draftPatch(root.category.id, null) }
            Ui.Button { text: "Restore default"; bordered: true; focusable: true; visible: !!root.category.default && root.presentationState !== "pending_handoff"; enabled: !root.busy; onClicked: root.draftPatch(root.category.id, ({ choice: root.category.default, install: false })) }
            Ui.Button { objectName: "cardDetailsAction"; text: root.cardDetailsOpen ? "Hide details" : "Details"; bordered: true; focusable: true; visible: root.presentationState !== "loading" && root.presentationState !== "applying"; onClicked: root.cardDetailsOpen = !root.cardDetailsOpen }
        }
    }

    Ui.ConfirmDialog {
        id: installDialog
        anchors.fill: parent
        Component.onCompleted: if ("confirmText" in installDialog) installDialog.confirmText = "Install and set"
        onCanceled: { opened = false; root.pendingChoice = null }
        onConfirmed: {
            opened = false
            if (root.pendingChoice) root.draftPatch(root.category.id, ({ choice: root.pendingChoice.id, install: true }))
            root.pendingChoice = null
        }
    }
}
