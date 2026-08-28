import QtQuick

QtObject {
    id: model

    property var backendClient: null
    property var history: []
    property var currentTransaction: null
    property var pinnedRecovery: null
    property var _currentPoll: null

    signal changed()

    function open() {
        refreshHistory()
        refreshCurrent()
    }

    function close() {
        if (_currentPoll && backendClient)
            backendClient.stopPolling(_currentPoll)
        _currentPoll = null
        currentTransaction = null
    }

    function refreshHistory(callback) {
        if (!backendClient)
            return
        backendClient.history(function(result) {
            if (result && result.ok) {
                history = result.data && (result.data.transactions || result.data.history) ? (result.data.transactions || result.data.history) : []
                _updatePinned()
            }
            if (callback) callback(result)
            changed()
        })
    }

    function transactionFromResult(result) {
        if (!result || !result.ok || !result.data)
            return null
        var record = result.data.transaction ? Object.assign({}, result.data.transaction) : Object.assign({}, result.data)
        if (result.data.confirmationToken)
            record.confirmationToken = result.data.confirmationToken
        if (result.data.confirmation)
            record.confirmation = result.data.confirmation
        return record
    }

    function refreshCurrent(callback) {
        if (!backendClient)
            return
        backendClient.transaction("current", function(result) {
            setCurrent(transactionFromResult(result))
            if (callback) callback(result)
        })
    }

    function setCurrent(transaction) {
        currentTransaction = transaction
        if (transaction && transaction.state === "rollback_failed")
            pinnedRecovery = transaction
        changed()
    }

    function watchCurrent(intervalMs) {
        if (!backendClient || _currentPoll)
            return
        _currentPoll = backendClient.pollTransaction("current", intervalMs || 250, function(result) {
            if (result && result.ok)
                setCurrent(transactionFromResult(result))
        })
    }

    function watchTransaction(transactionId, intervalMs) {
        if (!backendClient)
            return null
        return backendClient.pollTransaction(transactionId, intervalMs || 1000, function(result) {
            if (!result || !result.ok)
                return
            var transaction = result.data && result.data.transaction ? result.data.transaction : result.data
            if (transaction && transaction.state === "rollback_failed")
                pinnedRecovery = transaction
            refreshHistory()
        })
    }

    function _updatePinned() {
        var found = null
        for (var i = 0; i < history.length; ++i) {
            if (history[i].state === "rollback_failed") {
                found = history[i]
                break
            }
        }
        pinnedRecovery = found
    }

    readonly property bool applyBlocked: pinnedRecovery !== null
}
