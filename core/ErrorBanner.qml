import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui

Rectangle {
    id: root

    property string code: ""
    property string detail: ""
    readonly property string message: messageFor(code)
    readonly property var recoveryActions: recoveryFor(code)
    signal recoveryRequested(string action)

    visible: code !== "" && message !== ""
    color: Style.normalFillFor(Color.urgent, Color.accent)
    radius: Style.cornerRadius
    border.color: Style.normalBorderFor(Color.urgent, Color.accent)
    border.width: Style.normalBorderWidth
    implicitHeight: content.implicitHeight + Style.spacing.rowPaddingX * 2

    function messageFor(errorCode) {
        if (errorCode === "superseded") return ""
        var messages = {
            stale_revision: "The source changed since this draft was loaded.",
            validation_failed: "The draft contains values that cannot be applied.",
            invalid_draft: "The saved draft is not valid.",
            schema_version_unsupported: "This document was created by a newer schema version.",
            runtime_unavailable: "A required desktop service or command is unavailable.",
            capability_missing: "This action is not supported by the current desktop.",
            permission_required: "A target path is not writable.",
            unsupported_config: "The existing configuration cannot be managed safely.",
            resource_conflict: "Two requested changes need exclusive control of the same resource.",
            nonreversible_requires_confirmation: "This plan contains changes that require confirmation.",
            locked: "Another customization transaction is running.",
            timeout: "The backend command exceeded its time budget.",
            malformed_output: "The backend returned output that could not be read.",
            ipc_rejected: "The shell rejected the requested change.",
            handoff_failed: "The terminal action did not complete successfully.",
            verification_failed: "The applied state could not be verified and rollback ran.",
            rollback_failed: "Rollback did not finish. Further applies are blocked.",
            recovery_required: "A previous rollback must be repaired before applying changes.",
            transaction_not_found: "The transaction no longer exists.",
            transaction_state_invalid: "The transaction is no longer in the required state.",
            confirmation_invalid: "The confirmation token was rejected.",
            confirmation_expired: "The confirmation deadline passed and rollback started.",
            unknown_module: "The requested module is not installed.",
            unknown_query: "The requested module query is not available.",
            internal_error: "The backend encountered an unexpected error.",
            superseded: ""
        }
        return messages[errorCode] || (errorCode ? "An error occurred: " + errorCode : "")
    }

    function recoveryFor(errorCode) {
        var actions = {
            stale_revision: ["Reload", "Compare"],
            validation_failed: ["Review fields"],
            invalid_draft: ["Discard draft"],
            schema_version_unsupported: ["Open documentation"],
            runtime_unavailable: ["Retry", "Start shell"],
            capability_missing: ["Show capability"],
            permission_required: ["Show path"],
            unsupported_config: ["Open documentation"],
            resource_conflict: ["Show conflicts"],
            nonreversible_requires_confirmation: ["Review confirmations"],
            locked: ["Retry"],
            timeout: ["Retry"],
            malformed_output: ["Show output"],
            ipc_rejected: ["Retry"],
            handoff_failed: ["Retry"],
            verification_failed: ["Show rollback"],
            rollback_failed: ["Open recovery"],
            recovery_required: ["Open recovery"],
            transaction_not_found: ["Refresh history"],
            transaction_state_invalid: ["Refresh"],
            confirmation_invalid: [],
            confirmation_expired: ["Show rollback"],
            unknown_module: [],
            unknown_query: [],
            internal_error: ["Show logs"],
            superseded: []
        }
        return actions[errorCode] || []
    }

    ColumnLayout {
        id: content
        anchors.fill: parent
        anchors.margins: Style.spacing.rowPaddingX
        spacing: Style.spacing.md

        Text {
            Layout.fillWidth: true
            text: root.message
            color: Color.urgent
            font.family: Style.font.family
            font.pixelSize: Style.font.subtitle
            font.bold: true
            wrapMode: Text.WordWrap
        }
        Text {
            Layout.fillWidth: true
            visible: root.detail !== ""
            text: root.detail
            color: Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }
        RowLayout {
            spacing: Style.spacing.md
            Repeater {
                model: root.recoveryActions
                delegate: Ui.Button {
                    required property string modelData
                    text: modelData
                    bordered: true
                    focusable: true
                    onClicked: root.recoveryRequested(modelData)
                }
            }
        }
    }
}
