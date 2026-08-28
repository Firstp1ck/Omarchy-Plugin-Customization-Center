import QtQuick

QtObject {
    id: logic

    property var activeReads: ({})
    property var queuedReads: ({})
    property var mutationQueue: []

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

    function queueRead(moduleId, request) {
        var key = moduleId || "__global"
        if (activeReads[key]) {
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
