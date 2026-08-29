import QtQuick

QtObject {
    id: logic

    property var activeReads: ({})
    property var queuedReads: ({})
    property var mutationQueue: []
    readonly property int maximumMutationTimeoutMs: 15 * 60 * 1000

    function malformedResult(message, output) {
        return {
            schemaVersion: 1,
            ok: false,
            command: "backend",
            module: null,
            revision: null,
            data: { output: String(output || "").slice(0, 4096) },
            warnings: [],
            errors: [{ code: "malformed_output", message: message }],
            transactionId: null,
            durationMs: 0
        }
    }

    function parseLastJsonLine(stdoutText) {
        var lines = String(stdoutText || "").split(/\r?\n/)
        var parsed = null
        var parsedIndex = -1
        for (var i = 0; i < lines.length; ++i) {
            if (lines[i].trim() === "") continue
            try {
                var candidate = JSON.parse(lines[i])
                if (candidate !== null && typeof candidate === "object" && !Array.isArray(candidate)) {
                    parsed = candidate
                    parsedIndex = i
                }
            } catch (error) {
                // Diagnostics before the result line are intentionally ignored.
            }
        }
        if (parsedIndex < 0)
            return malformedResult("No JSON object was found on the final output line", stdoutText)
        for (var j = parsedIndex + 1; j < lines.length; ++j) {
            if (lines[j].trim() !== "")
                return malformedResult("Output followed the JSON result", stdoutText)
        }
        return parsed
    }

    function supersededResult(command, moduleId) {
        return {
            schemaVersion: 1,
            ok: false,
            command: command || "read",
            module: moduleId || null,
            revision: null,
            data: null,
            warnings: [],
            errors: [{ code: "superseded", message: "A newer read request replaced this queued request" }],
            transactionId: null,
            durationMs: 0
        }
    }

    function queueRead(moduleId, request) {
        var key = moduleId || "__global"
        if (activeReads[key]) {
            var displaced = queuedReads[key]
            if (displaced && typeof displaced.callback === "function")
                displaced.callback(supersededResult(displaced.command, displaced.moduleId))
            var queued = Object.assign({}, queuedReads)
            queued[key] = request
            queuedReads = queued
            return false
        }
        var active = Object.assign({}, activeReads)
        active[key] = request
        activeReads = active
        return true
    }

    function firstErrorCode(result) {
        return result && result.errors && result.errors.length ? String(result.errors[0].code || "") : ""
    }

    function resolveRollbackPlan(transactionId, lookupBackend, callback, attempt) {
        var retryCount = attempt || 0
        lookupBackend.transaction(transactionId, function(result) {
            if ((!result || !result.ok) && firstErrorCode(result) === "superseded" && retryCount < 1) {
                Qt.callLater(function() {
                    logic.resolveRollbackPlan(transactionId, lookupBackend, callback, retryCount + 1)
                })
                return
            }
            if (!result || !result.ok) {
                callback({
                    plan: ({}),
                    forceMaximumTimeout: true,
                    logLine: "Rollback plan could not be read for transaction " + transactionId + "; using the maximum timeout"
                })
                return
            }
            var record = result.data && result.data.transaction ? result.data.transaction : result.data
            callback({
                plan: record && record.plan ? record.plan : ({}),
                forceMaximumTimeout: false,
                logLine: ""
            })
        })
    }

    function isRead(command) {
        return ["modules", "capabilities", "status", "validate", "plan", "query", "history", "transaction"].indexOf(command) >= 0
    }

    function timeoutFor(command, plan, forceMaximum) {
        if (forceMaximum && (command === "apply" || command === "rollback"))
            return maximumMutationTimeoutMs
        if (["modules", "capabilities", "status", "history", "transaction", "confirm"].indexOf(command) >= 0)
            return 10000
        if (["validate", "plan", "query", "abandon", "restore", "resolve", "draft-asset-add"].indexOf(command) >= 0)
            return 30000
        if (command === "recover")
            return maximumMutationTimeoutMs
        if (command === "apply" || command === "rollback") {
            var total = 15000
            var operations = plan && plan.operations ? plan.operations : []
            for (var i = 0; i < operations.length; ++i) {
                total += Number(operations[i].timeoutS || operations[i].timeout_s || 30) * 1000
                if (operations[i].kind === "TimedConfirmation")
                    total += Number(operations[i].params && operations[i].params.seconds || 0) * 1000
            }
            return Math.min(maximumMutationTimeoutMs, Math.max(30000, total))
        }
        return 10000
    }

    function buildApplyArgv(moduleId, revision, digest, confirmations) {
        var argv = ["apply", moduleId, "--draft", "-", "--expected-revision", revision, "--plan-digest", digest]
        var keys = confirmations || []
        for (var i = 0; i < keys.length; ++i)
            argv.push("--confirm", keys[i])
        return argv
    }

    function buildAbandonArgv(transactionId) { return ["abandon", transactionId] }
    function buildRecoverArgv() { return ["recover"] }
    function buildRestoreArgv(transactionId, path) { return ["restore", transactionId, "--path", path] }
    function buildResolveArgv(transactionId, operationId) { return ["resolve", transactionId, "--operation", operationId] }
    function buildCapabilitiesArgv(moduleId) {
        return moduleId ? ["capabilities", moduleId] : ["capabilities"]
    }
    function buildHistoryFilteredArgv(moduleId, limit, state) {
        var argv = ["history"]
        if (moduleId)
            argv.push("--module", moduleId)
        if (limit !== undefined && limit !== null && String(limit) !== "")
            argv.push("--limit", String(limit))
        if (state)
            argv.push("--state", state)
        return argv
    }
    function buildDraftAssetAddArgv(moduleId, path) { return ["draft", "asset-add", moduleId, "--path", path] }

    function finishRead(moduleId) {
        var key = moduleId || "__global"
        var active = Object.assign({}, activeReads)
        delete active[key]
        activeReads = active
        var next = queuedReads[key] || null
        if (next) {
            var queued = Object.assign({}, queuedReads)
            delete queued[key]
            queuedReads = queued
            active = Object.assign({}, activeReads)
            active[key] = next
            activeReads = active
        }
        return next
    }

    function enqueueMutation(request) {
        var queue = mutationQueue.slice()
        queue.push(request)
        mutationQueue = queue
    }

    function takeMutation() {
        if (!mutationQueue.length) return null
        var queue = mutationQueue.slice()
        var next = queue.shift()
        mutationQueue = queue
        return next
    }
}
