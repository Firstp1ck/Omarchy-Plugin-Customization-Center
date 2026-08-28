import QtQuick

QtObject {
    id: logic

    property var backendClient: null
    property var transaction: null
    readonly property bool active: transaction && transaction.state === "awaiting_confirmation"
    readonly property string confirmationToken: transaction && transaction.confirmationToken ? String(transaction.confirmationToken) : ""
    readonly property bool canConfirm: active && confirmationToken !== ""

    signal confirmationFinished(var result)

    function confirmCurrent() {
        if (!canConfirm || !backendClient)
            return false
        backendClient.confirm(transaction.id, confirmationToken, function(result) {
            logic.confirmationFinished(result)
        })
        return true
    }
}
