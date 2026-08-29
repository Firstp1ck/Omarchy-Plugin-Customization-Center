import QtQuick

QtObject {
    id: model

    property var backendClient: null
    property var history: []
    property var currentTransaction: null
    property var pinnedRecovery: null
    property var _currentPoll: null
    property bool recoveryBusy: false

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

    function rollbackErrors(transaction) {
        if (!transaction)
            return []
        var data = transaction.data || transaction
        return data.rollbackErrors || data.rollback_errors || transaction.rollbackErrors || transaction.rollback_errors || []
    }

    function backupPaths(transaction) {
        if (!transaction)
            return []
        var data = transaction.data || transaction
        if (data.backupPaths)
            return data.backupPaths
        var backups = transaction.backups || data.backups || ({})
        return Object.keys(backups)
    }

    function manualPaths(transaction) {
        if (!transaction)
            return []
        var data = transaction.data || transaction
        if (data.manualPaths)
            return data.manualPaths
        var backups = backupPaths(transaction)
        var paths = []
        var errors = rollbackErrors(transaction)
        for (var i = 0; i < errors.length; ++i) {
            var affected = errors[i].affectedPaths || errors[i].affected_paths || []
            for (var j = 0; j < affected.length; ++j) {
                if (backups.indexOf(affected[j]) < 0)
                    paths.push({ operationId: errors[i].operationId || errors[i].operation_id || "", path: affected[j] })
            }
        }
        return paths
    }

    function resolveOperations(transaction) {
        var operations = []
        var seen = ({})
        var errors = rollbackErrors(transaction)
        var backups = backupPaths(transaction)
        for (var i = 0; i < errors.length; ++i) {
            var error = errors[i]
            if (error.resolved)
                continue
            var operationId = error.operationId || error.operation_id || ""
            var affected = error.affectedPaths || error.affected_paths || []
            var hasNonFilePath = affected.length === 0
            for (var j = 0; j < affected.length; ++j) {
                if (backups.indexOf(affected[j]) < 0)
                    hasNonFilePath = true
            }
            if (operationId && hasNonFilePath && !seen[operationId]) {
                seen[operationId] = true
                operations.push(operationId)
            }
        }
        return operations
    }

    function needsRecovery(transaction) {
        if (!transaction || transaction.state !== "rollback_failed")
            return false
        var errors = rollbackErrors(transaction)
        if (!errors.length)
            return true
        for (var i = 0; i < errors.length; ++i) {
            if (!errors[i].resolved)
                return true
        }
        return false
    }

    function setCurrent(transaction) {
        currentTransaction = transaction
        if (needsRecovery(transaction))
            pinnedRecovery = transaction
        changed()
    }

    function refreshPinnedRecovery(transactionId, callback) {
        if (!backendClient || !transactionId)
            return
        backendClient.transaction(transactionId, function(result) {
            var transaction = transactionFromResult(result)
            if (transaction && transaction.id === transactionId) {
                pinnedRecovery = needsRecovery(transaction) ? transaction : null
                changed()
            }
            if (callback) callback(result)
        })
    }

    function restore(path, callback) {
        if (!backendClient || !pinnedRecovery || !pinnedRecovery.id || recoveryBusy)
            return false
        var transactionId = pinnedRecovery.id
        recoveryBusy = true
        backendClient.restore(transactionId, path, function(result) {
            recoveryBusy = false
            refreshPinnedRecovery(transactionId, function() {
                if (callback) callback(result)
            })
        })
        return true
    }

    function resolve(operationId, callback) {
        if (!backendClient || !pinnedRecovery || !pinnedRecovery.id || recoveryBusy)
            return false
        var transactionId = pinnedRecovery.id
        recoveryBusy = true
        backendClient.resolve(transactionId, operationId, function(result) {
            recoveryBusy = false
            refreshPinnedRecovery(transactionId, function() {
                if (callback) callback(result)
            })
        })
        return true
    }

    function recover(callback) {
        if (!backendClient || recoveryBusy)
            return false
        recoveryBusy = true
        backendClient.recover(function(result) {
            recoveryBusy = false
            refreshHistory(function() {
                if (callback) callback(result)
            })
        })
        return true
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
            if (needsRecovery(transaction))
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
        if (!found) {
            pinnedRecovery = null
            return
        }
        if (pinnedRecovery && pinnedRecovery.id === found.id) {
            if (!needsRecovery(pinnedRecovery))
                pinnedRecovery = null
            return
        }
        pinnedRecovery = found
        refreshPinnedRecovery(found.id)
    }

    readonly property bool applyBlocked: pinnedRecovery !== null
}
