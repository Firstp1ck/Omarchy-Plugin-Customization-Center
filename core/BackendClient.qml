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
    property bool _mutationActive: false
    property var _pollers: []
    property int _nextRequestId: 1
    property BackendLogic logic: BackendLogic {}

    signal requestStarted(int requestId, string command, string moduleId)
    signal requestFinished(int requestId, string command, string moduleId, var result)
    signal pendingHandoffReconciled(string transactionId, var result)

    function timeoutFor(command, plan) {
        if (["modules", "capabilities", "status", "history", "transaction", "confirm"].indexOf(command) >= 0)
            return 10000
        if (["validate", "plan", "query"].indexOf(command) >= 0)
            return 30000
        if (command === "apply" || command === "rollback") {
            var total = 15000
            var operations = plan && plan.operations ? plan.operations : []
            for (var i = 0; i < operations.length; ++i) {
                total += Number(operations[i].timeoutS || operations[i].timeout_s || 30) * 1000
                if (operations[i].kind === "TimedConfirmation")
                    total += Number(operations[i].params && operations[i].params.seconds || 0) * 1000
            }
            return Math.min(15 * 60 * 1000, Math.max(30000, total))
        }
        return 10000
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
        return ["modules", "capabilities", "status", "validate", "plan", "query", "history", "transaction"].indexOf(command) >= 0
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
        process.running = true
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
    function status(moduleId, callback) { return call("status", ["status", moduleId], moduleId, "", callback) }
    function history(callback) { return call("history", ["history", "--limit", "50"], "", "", callback) }
    function validate(moduleId, draft, callback) { return call("validate", ["validate", moduleId, "--draft", "-"], moduleId, JSON.stringify(draft || {}), callback) }
    function plan(moduleId, draft, callback) { return call("plan", ["plan", moduleId, "--draft", "-"], moduleId, JSON.stringify(draft || {}), callback) }
    function query(moduleId, name, args, callback) { return call("query", ["query", moduleId, name, "--args", "-"], moduleId, JSON.stringify(args || {}), callback) }
    function apply(moduleId, draft, revision, digest, confirmations, planData, callback) {
        var argv = ["apply", moduleId, "--draft", "-", "--expected-revision", revision, "--plan-digest", digest]
        var keys = confirmations || []
        for (var i = 0; i < keys.length; ++i)
            argv.push("--confirm", keys[i])
        return call("apply", argv, moduleId, JSON.stringify(draft || {}), callback, { plan: planData || {} })
    }
    function rollback(transactionId, reason, callback) { return call("rollback", ["rollback", transactionId, "--reason", reason || "user"], "", "", callback) }
    function confirm(transactionId, token, callback) { return call("confirm", ["confirm", transactionId, "--token", token], "", "", callback) }
    function transaction(transactionId, callback) { return call("transaction", ["transaction", transactionId], "", "", callback) }
    function reconcile(transactionId, callback) { return call("reconcile", ["reconcile", transactionId], "", "", function(result) { pendingHandoffReconciled(transactionId, result); if (callback) callback(result) }) }
    function draftLoad(moduleId, callback) { return call("draft-load", ["draft", "load", moduleId], moduleId, "", callback) }
    function draftSave(moduleId, draft, callback) { return call("draft-save", ["draft", "save", moduleId, "--draft", "-"], moduleId, JSON.stringify(draft || {}), callback) }
    function draftDiscard(moduleId, callback) { return call("draft-discard", ["draft", "discard", moduleId], moduleId, "", callback) }

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

    function _reconcilePendingFromStatus(result) {
        var pending = result && result.data && result.data.pendingHandoffs ? result.data.pendingHandoffs : []
        for (var i = 0; i < pending.length; ++i) {
            var row = pending[i]
            if (row && row.sentinelExists === true && row.id)
                reconcile(row.id)
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
                        client._reconcilePendingFromStatus(result)
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
                    }
                }
            }
            stderr: StdioCollector {
                waitForEnd: true
                onDataChanged: backendProcess.stderrText = text
            }
            property Timer timeoutTimer: Timer {
                interval: backendProcess.request ? client.timeoutFor(backendProcess.request.command, backendProcess.request.options.plan) : 10000
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
            onStarted: {
                timeoutTimer.start()
                if (request.stdinText !== "") {
                    write(request.stdinText)
                    stdinEnabled = false
                }
            }
            onExited: function(exitCode) {
                timeoutTimer.stop()
                killTimer.stop()
                client._processExited(backendProcess, exitCode)
            }
        }
    }
}
