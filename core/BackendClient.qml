import QtQuick
import Quickshell.Io

QtObject {
    id: client

    property string ccctlPath: ""
    property string omarchyPath: ""
    property bool acceptingRequests: true
    readonly property int outputLimit: 8 * 1024 * 1024
    readonly property int stderrLineLimit: 200
    property var stderrByModule: ({})
    property var _reconcilingHandoffs: ({})
    property bool _mutationActive: false
    property var _pollers: []
    property int _nextRequestId: 1
    property BackendLogic logic: BackendLogic {}

    signal requestStarted(int requestId, string command, string moduleId)
    signal requestFinished(int requestId, string command, string moduleId, var result)
    signal pendingHandoffReconciled(string transactionId, var result)

    function timeoutFor(command, plan, forceMaximum) {
        return logic.timeoutFor(command, plan, forceMaximum)
    }

    function parseLastJsonLine(stdoutText) {
        return logic.parseLastJsonLine(stdoutText)
    }

    function malformedResult(message, output) {
        return logic.malformedResult(message, output)
    }

    function errorResult(code, message, command, moduleId) {
        var result = malformedResult(message, "")
        result.command = command
        result.module = moduleId || null
        result.errors = [{ code: code, message: message }]
        return result
    }

    function isRead(command) {
        return logic.isRead(command)
    }

    function call(command, argv, moduleId, stdinText, callback, options) {
        var request = {
            id: _nextRequestId++,
            command: command,
            argv: argv || [],
            moduleId: moduleId || "",
            stdinText: stdinText === undefined || stdinText === null ? "" : String(stdinText),
            callback: callback,
            options: options || ({})
        }
        if (!acceptingRequests && command !== "confirm") {
            _deliver(request, errorResult("runtime_unavailable", "The overlay is closing", command, moduleId))
            return request.id
        }
        if (command === "confirm") {
            _dispatch(request)
            return request.id
        }
        if (isRead(command)) {
            if (logic.queueRead(request.moduleId, request))
                _dispatch(request)
            return request.id
        }
        logic.enqueueMutation(request)
        _startNextMutation()
        return request.id
    }

    function _startNextMutation() {
        if (_mutationActive)
            return
        var request = logic.takeMutation()
        if (!request)
            return
        _mutationActive = true
        _dispatch(request)
    }

    function _dispatch(request) {
        if (!ccctlPath) {
            _requestDone(request, errorResult("runtime_unavailable", "Backend path is empty", request.command, request.moduleId))
            return
        }
        requestStarted(request.id, request.command, request.moduleId)
        var process = processComponent.createObject(client, { request: request })
        if (!process) {
            _requestDone(request, errorResult("internal_error", "Could not create backend process", request.command, request.moduleId))
            return
        }
        process.launch()
    }

    function _processStartFailed(process) {
        if (process.completed)
            return
        process.completed = true
        process.timeoutTimer.stop()
        process.killTimer.stop()
        var request = process.request
        var result = errorResult("runtime_unavailable", "Backend executable could not be started: " + ccctlPath, request.command, request.moduleId)
        process.destroy()
        _requestDone(request, result)
    }

    function _processExited(process, exitCode) {
        var request = process.request
        var result
        if (process.oversized) {
            result = errorResult("malformed_output", "Backend output exceeded 8 MiB", request.command, request.moduleId)
        } else if (process.timedOut) {
            result = errorResult("timeout", request.command + " exceeded its time budget", request.command, request.moduleId)
        } else {
            result = parseLastJsonLine(process.stdoutText)
            if (exitCode !== 0 && result.ok === true)
                result = errorResult("malformed_output", "Backend exited " + exitCode + " with a successful result", request.command, request.moduleId)
        }
        _rememberStderr(request.moduleId, process.stderrText)
        process.destroy()
        _requestDone(request, result)
    }

    function _requestDone(request, result) {
        _deliver(request, result)
        if (isRead(request.command)) {
            var queued = logic.finishRead(request.moduleId)
            if (queued)
                _dispatch(queued)
        } else if (request.command !== "confirm") {
            _mutationActive = false
            _startNextMutation()
        }
    }

    function _deliver(request, result) {
        requestFinished(request.id, request.command, request.moduleId, result)
        if (typeof request.callback === "function")
            request.callback(result)
    }

    function _rememberStderr(moduleId, text) {
        if (!text)
            return
        var key = moduleId || "core"
        var previous = stderrByModule[key] || []
        var incoming = String(text).split(/\r?\n/).filter(function(line) { return line !== "" })
        var next = previous.concat(incoming)
        if (next.length > stderrLineLimit)
            next = next.slice(next.length - stderrLineLimit)
        var all = Object.assign({}, stderrByModule)
        all[key] = next
        stderrByModule = all
    }

    function modules(callback) { return call("modules", ["modules"], "", "", callback) }
    function status(moduleId, callback) {
        return call("status", ["status", moduleId], moduleId, "", function(result) {
            _reconcilePendingFromStatus(result)
            if (callback) callback(result)
        })
    }
    function history(callback) { return call("history", logic.buildHistoryFilteredArgv("", 50, ""), "", "", callback) }
    function historyFiltered(moduleId, limit, state, callback) {
        return call("history", logic.buildHistoryFilteredArgv(moduleId, limit, state), moduleId, "", callback)
    }
    function capabilities(moduleId, callback) {
        return call("capabilities", logic.buildCapabilitiesArgv(moduleId), moduleId, "", callback)
    }
    function validate(moduleId, draft, callback) { return call("validate", ["validate", moduleId, "--draft", "-"], moduleId, JSON.stringify(draft || {}), callback) }
    function plan(moduleId, draft, callback) { return call("plan", ["plan", moduleId, "--draft", "-"], moduleId, JSON.stringify(draft || {}), callback) }
    function query(moduleId, name, args, callback) { return call("query", ["query", moduleId, name, "--args", "-"], moduleId, JSON.stringify(args || {}), callback) }
    function apply(moduleId, draft, revision, digest, confirmations, planData, callback) {
        return call("apply", logic.buildApplyArgv(moduleId, revision, digest, confirmations), moduleId, JSON.stringify(draft || {}), callback, { plan: planData || {} })
    }
    function rollback(transactionId, reason, callback, planData) {
        if (planData)
            return call("rollback", ["rollback", transactionId, "--reason", reason || "user"], "", "", callback, { plan: planData })
        logic.resolveRollbackPlan(transactionId, client, function(decision) {
            if (decision.logLine)
                _rememberStderr("", decision.logLine)
            call("rollback", ["rollback", transactionId, "--reason", reason || "user"], "", "", callback, {
                plan: decision.plan,
                forceMaximumTimeout: decision.forceMaximumTimeout
            })
        })
        return 0
    }
    function confirm(transactionId, token, callback) {
        if (!token) {
            var result = errorResult("confirmation_invalid", "Confirmation token is unavailable", "confirm", "")
            if (callback) callback(result)
            return 0
        }
        return call("confirm", ["confirm", transactionId, "--token", token], "", "", callback)
    }
    function transaction(transactionId, callback) { return call("transaction", ["transaction", transactionId], "", "", callback) }
    function reconcile(transactionId, callback) { return call("reconcile", ["reconcile", transactionId], "", "", function(result) { pendingHandoffReconciled(transactionId, result); if (callback) callback(result) }) }
    function abandon(transactionId, callback) { return call("abandon", logic.buildAbandonArgv(transactionId), "", "", callback) }
    function recover(callback) { return call("recover", logic.buildRecoverArgv(), "", "", callback) }
    function restore(transactionId, path, callback) { return call("restore", logic.buildRestoreArgv(transactionId, path), "", "", callback) }
    function resolve(transactionId, operationId, callback) { return call("resolve", logic.buildResolveArgv(transactionId, operationId), "", "", callback) }
    function draftLoad(moduleId, callback) { return call("draft-load", ["draft", "load", moduleId], moduleId, "", callback) }
    function draftSave(moduleId, draft, callback) { return call("draft-save", ["draft", "save", moduleId, "--draft", "-"], moduleId, JSON.stringify(draft || {}), callback) }
    function draftDiscard(moduleId, callback) { return call("draft-discard", ["draft", "discard", moduleId], moduleId, "", callback) }
    function draftAssetAdd(moduleId, path, callback) { return call("draft-asset-add", logic.buildDraftAssetAddArgv(moduleId, path), moduleId, "", callback) }

    function pollTransaction(transactionId, intervalMs, callback) {
        return _newPoller("transaction", transactionId, intervalMs, callback)
    }

    function pollStatus(moduleId, intervalMs, callback) {
        return _newPoller("status", moduleId, intervalMs, callback)
    }

    function _newPoller(kind, target, intervalMs, callback) {
        var poller = pollerComponent.createObject(client, {
            pollKind: kind,
            target: target,
            interval: Math.max(200, intervalMs || 1000),
            callback: callback
        })
        var all = _pollers.slice()
        all.push(poller)
        _pollers = all
        poller.trigger()
        return poller
    }

    function stopPolling(handle) {
        if (!handle)
            return
        handle.stop()
        var all = _pollers.filter(function(item) { return item !== handle })
        _pollers = all
        handle.destroy()
    }

    function stopAllPolling() {
        var all = _pollers.slice()
        _pollers = []
        for (var i = 0; i < all.length; ++i) {
            all[i].stop()
            all[i].destroy()
        }
    }

    function _reconcileCallback(transactionId) {
        return function() {
            var remaining = Object.assign({}, client._reconcilingHandoffs)
            delete remaining[transactionId]
            client._reconcilingHandoffs = remaining
        }
    }

    function _reconcilePendingFromStatus(result) {
        var pending = result && result.data && result.data.pendingHandoffs ? result.data.pendingHandoffs : []
        for (var i = 0; i < pending.length; ++i) {
            var row = pending[i]
            if (row && row.sentinelExists === true && row.id && !_reconcilingHandoffs[row.id]) {
                var active = Object.assign({}, _reconcilingHandoffs)
                active[row.id] = true
                _reconcilingHandoffs = active
                reconcile(row.id, _reconcileCallback(row.id))
            }
        }
    }

    property Component pollerComponent: Component {
        Timer {
            property string pollKind: ""
            property string target: ""
            property var callback: null
            repeat: true
            function trigger() {
                if (pollKind === "status") {
                    client.status(target, function(result) {
                        if (callback) callback(result)
                    })
                } else {
                    client.transaction(target, callback)
                }
                restart()
            }
            onTriggered: trigger()
        }
    }

    property Component processComponent: Component {
        Process {
            id: backendProcess
            property var request: null
            property string stdoutText: ""
            property string stderrText: ""
            property bool oversized: false
            property bool timedOut: false
            property bool launchAttempted: false
            property bool startedObserved: false
            property bool completed: false
            command: [client.ccctlPath].concat(request ? request.argv : [])
            environment: ({ "OMARCHY_PATH": client.omarchyPath, "CC_CALLER": "overlay" })
            stdinEnabled: request && request.stdinText !== ""
            stdout: StdioCollector {
                waitForEnd: true
                onDataChanged: {
                    backendProcess.stdoutText = text
                    if (data.length > client.outputLimit && !backendProcess.oversized) {
                        backendProcess.oversized = true
                        backendProcess.signal(15)
                        killTimer.start()
                    }
                }
            }
            stderr: StdioCollector {
                waitForEnd: true
                onDataChanged: backendProcess.stderrText = text
            }
            property Timer timeoutTimer: Timer {
                interval: backendProcess.request ? client.timeoutFor(backendProcess.request.command, backendProcess.request.options.plan, backendProcess.request.options.forceMaximumTimeout === true) : 10000
                repeat: false
                onTriggered: {
                    backendProcess.timedOut = true
                    backendProcess.signal(15)
                    killTimer.start()
                }
            }
            property Timer killTimer: Timer {
                id: killTimer
                interval: 2000
                repeat: false
                onTriggered: if (backendProcess.running) backendProcess.signal(9)
            }
            property Timer startFailureTimer: Timer {
                interval: 100
                repeat: false
                onTriggered: {
                    if (backendProcess.launchAttempted && !backendProcess.startedObserved && !backendProcess.running)
                        client._processStartFailed(backendProcess)
                }
            }
            function launch() {
                launchAttempted = true
                timeoutTimer.start()
                running = true
                startFailureTimer.restart()
            }
            onStarted: {
                startedObserved = true
                startFailureTimer.stop()
                if (request.stdinText !== "") {
                    write(request.stdinText)
                    stdinEnabled = false
                }
            }
            onRunningChanged: {
                if (launchAttempted && !running && !startedObserved && !completed)
                    startFailureTimer.restart()
            }
            onExited: function(exitCode) {
                if (completed)
                    return
                completed = true
                timeoutTimer.stop()
                killTimer.stop()
                startFailureTimer.stop()
                client._processExited(backendProcess, exitCode)
            }
        }
    }
}
