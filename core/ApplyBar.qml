import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

Ui.BorderSurface {
    id: root

    property var backendClient: null
    property var draftStore: null
    property var transactionModel: null
    property string moduleId: ""
    property var status: null
    property var planData: null
    property var validation: null
    property var reviewedDraft: null
    property bool busy: false
    property bool reviewing: planData !== null
    property string errorCode: ""
    property string errorMessage: ""
    property var _confirmationKeys: []
    property var _confirmedKeys: []

    signal applied(string transactionId, var result)
    signal resetCompleted()
    signal reviewOpened(var plan)

    color: Color.popups.background
    borderSpec: Border.localOrSurfaceSpec("popups", "border", Color.popups.border, Color.popups.border, Style.normalBorderWidth)
    implicitHeight: controls.implicitHeight + Style.spacing.rowPaddingX * 2

    function resultError(result) {
        return result && result.errors && result.errors.length ? result.errors[0] : ({ code: "internal_error", message: "Backend request failed" })
    }

    function review() {
        if (!backendClient || !moduleId || busy)
            return
        busy = true
        planData = null
        validation = null
        reviewedDraft = null
        _confirmationKeys = []
        _confirmedKeys = []
        errorCode = ""
        errorMessage = ""
        var draft = draftStore ? draftStore.draftFor(moduleId) : ({})
        backendClient.validate(moduleId, draft, function(validateResult) {
            if (!validateResult || !validateResult.ok) {
                busy = false
                var validateError = resultError(validateResult)
                errorCode = validateError.code
                errorMessage = validateError.message
                return
            }
            validation = validateResult.data
            var normalized = validateResult.data && validateResult.data.normalizedDraft ? validateResult.data.normalizedDraft : draft
            reviewedDraft = normalized
            backendClient.plan(moduleId, normalized, function(planResult) {
                busy = false
                if (!planResult || !planResult.ok) {
                    var planError = resultError(planResult)
                    errorCode = planError.code
                    errorMessage = planError.message
                    return
                }
                planData = planResult.data && planResult.data.plan ? planResult.data.plan : planResult.data
                reviewOpened(planData)
            })
        })
    }

    function requestApply() {
        if (!planData) {
            review()
            return
        }
        _confirmationKeys = planData.requiresConfirmation || planData.requires_confirmation || []
        _confirmedKeys = []
        if (_confirmationKeys.length)
            showNextConfirmation()
        else
            runApply()
    }

    function showNextConfirmation() {
        if (_confirmedKeys.length >= _confirmationKeys.length) {
            runApply()
            return
        }
        confirmDialog.itemName = String(_confirmationKeys[_confirmedKeys.length])
        confirmDialog.message = "Type the confirmation key exactly to acknowledge this change."
        confirmDialog.requireTypedName = true
        confirmDialog.open()
    }

    function runApply() {
        if (!backendClient || !planData || busy)
            return
        busy = true
        errorCode = ""
        if (transactionModel)
            transactionModel.watchCurrent(250)
        var draft = reviewedDraft || (validation && validation.normalizedDraft) || (draftStore ? draftStore.draftFor(moduleId) : ({}))
        var revision = status && status.revision ? status.revision : (planData.expectedRevision || planData.expected_revision || "")
        var digest = planData.planDigest || planData.plan_digest || ""
        backendClient.apply(moduleId, draft, revision, digest, _confirmedKeys, planData, function(result) {
            busy = false
            if (!result || !result.ok) {
                var applyError = resultError(result)
                errorCode = applyError.code
                errorMessage = applyError.message
                if (transactionModel) transactionModel.refreshHistory()
                return
            }
            var transactionId = result.transactionId || (result.data && result.data.transactionId) || ""
            if (draftStore) draftStore.discard(moduleId)
            planData = null
            reviewedDraft = null
            if (transactionModel) transactionModel.refreshHistory()
            applied(transactionId, result)
        })
    }

    function resetDraft() {
        if (!draftStore || !moduleId || busy)
            return
        draftStore.discard(moduleId, function() { root.resetCompleted() })
        planData = null
        reviewedDraft = null
    }

    RowLayout {
        id: controls
        anchors.fill: parent
        anchors.margins: Style.spacing.rowPaddingX
        spacing: Style.spacing.md

        Text {
            Layout.fillWidth: true
            text: root.reviewing ? (root.planData.summary || "Review changes") : (root.draftStore && root.draftStore.isDirty(root.moduleId) ? "Draft has unapplied changes" : "No pending review")
            color: Color.popups.text
            font.family: Style.font.family
            font.pixelSize: Style.font.body
            elide: Text.ElideRight
        }
        Ui.Button {
            text: "Reset"
            bordered: true
            focusable: true
            enabled: !root.busy && root.draftStore && root.draftStore.isDirty(root.moduleId)
            onClicked: root.resetDraft()
        }
        Ui.Button {
            text: "Review"
            bordered: true
            focusable: true
            enabled: !root.busy && root.moduleId !== "" && !(root.transactionModel && root.transactionModel.applyBlocked)
            onClicked: root.review()
        }
        Ui.Button {
            text: "Apply"
            bordered: true
            focusable: true
            enabled: !root.busy && root.planData !== null && !(root.transactionModel && root.transactionModel.applyBlocked)
            onClicked: root.requestApply()
        }
    }

    ConfirmDialog {
        id: confirmDialog
        anchors.fill: parent
        onConfirmed: {
            var next = root._confirmedKeys.slice()
            next.push(root._confirmationKeys[next.length])
            root._confirmedKeys = next
            root.showNextConfirmation()
        }
    }
}
