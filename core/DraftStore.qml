import QtQuick

QtObject {
    id: store

    property var backendClient: null
    property string activeModuleId: ""
    property bool shortcutsEnabled: true
    property var drafts: ({})
    property var dirty: ({})
    property var loaded: ({})
    property var _undoStacks: ({})
    property var _redoStacks: ({})
    property var _saveTimers: ({})
    readonly property int historyDepth: 100

    signal draftUpdated(string moduleId, var draft)
    signal saveFailed(string moduleId, var result)

    function clone(value) {
        if (value === undefined)
            return undefined
        return JSON.parse(JSON.stringify(value))
    }

    function isObject(value) {
        return value !== null && typeof value === "object" && !Array.isArray(value)
    }

    function mergePatch(target, patch) {
        if (!isObject(patch))
            return clone(patch)
        var output = isObject(target) ? clone(target) : ({})
        var keys = Object.keys(patch)
        for (var i = 0; i < keys.length; ++i) {
            var key = keys[i]
            if (patch[key] === null)
                delete output[key]
            else if (isObject(patch[key]))
                output[key] = mergePatch(output[key], patch[key])
            else
                output[key] = clone(patch[key])
        }
        return output
    }

    function draftFor(moduleId) {
        return drafts[moduleId] || ({})
    }

    function isDirty(moduleId) {
        return dirty[moduleId] === true
    }

    function load(moduleId, callback) {
        if (loaded[moduleId]) {
            if (callback) callback(draftFor(moduleId))
            return
        }
        if (!backendClient) {
            _setDraft(moduleId, {}, false)
            if (callback) callback(draftFor(moduleId))
            return
        }
        backendClient.draftLoad(moduleId, function(result) {
            var value = {}
            if (result && result.ok && result.data) {
                if (result.data.draft && result.data.draft.draft)
                    value = result.data.draft.draft
                else if (result.data.draft)
                    value = result.data.draft
                else if (result.data.document && result.data.document.draft)
                    value = result.data.document.draft
            }
            _setDraft(moduleId, value, false)
            var allLoaded = Object.assign({}, loaded)
            allLoaded[moduleId] = true
            loaded = allLoaded
            if (callback) callback(draftFor(moduleId))
        })
    }

    function applyPatch(moduleId, patch) {
        var before = clone(draftFor(moduleId))
        var after = mergePatch(before, patch)
        if (JSON.stringify(before) === JSON.stringify(after))
            return
        _pushUndo(moduleId, before)
        var redo = Object.assign({}, _redoStacks)
        redo[moduleId] = []
        _redoStacks = redo
        _setDraft(moduleId, after, true)
        _scheduleSave(moduleId)
    }

    function replace(moduleId, value, recordHistory) {
        if (recordHistory !== false)
            _pushUndo(moduleId, clone(draftFor(moduleId)))
        _setDraft(moduleId, value || {}, true)
        _scheduleSave(moduleId)
    }

    function _setDraft(moduleId, value, markDirty) {
        var allDrafts = Object.assign({}, drafts)
        allDrafts[moduleId] = clone(value || {})
        drafts = allDrafts
        var allDirty = Object.assign({}, dirty)
        allDirty[moduleId] = markDirty === true
        dirty = allDirty
        draftUpdated(moduleId, allDrafts[moduleId])
    }

    function _pushUndo(moduleId, snapshot) {
        var stacks = Object.assign({}, _undoStacks)
        var stack = (stacks[moduleId] || []).slice()
        stack.push(snapshot)
        if (stack.length > historyDepth)
            stack.shift()
        stacks[moduleId] = stack
        _undoStacks = stacks
    }

    function canUndo(moduleId) { return (_undoStacks[moduleId] || []).length > 0 }
    function canRedo(moduleId) { return (_redoStacks[moduleId] || []).length > 0 }

    function undo(moduleId) {
        var key = moduleId || activeModuleId
        var stack = (_undoStacks[key] || []).slice()
        if (stack.length === 0)
            return false
        var previous = stack.pop()
        var undoStacks = Object.assign({}, _undoStacks)
        undoStacks[key] = stack
        _undoStacks = undoStacks
        var redoStacks = Object.assign({}, _redoStacks)
        var redo = (redoStacks[key] || []).slice()
        redo.push(clone(draftFor(key)))
        redoStacks[key] = redo
        _redoStacks = redoStacks
        _setDraft(key, previous, true)
        _scheduleSave(key)
        return true
    }

    function redo(moduleId) {
        var key = moduleId || activeModuleId
        var stack = (_redoStacks[key] || []).slice()
        if (stack.length === 0)
            return false
        var next = stack.pop()
        var redoStacks = Object.assign({}, _redoStacks)
        redoStacks[key] = stack
        _redoStacks = redoStacks
        _pushUndo(key, clone(draftFor(key)))
        _setDraft(key, next, true)
        _scheduleSave(key)
        return true
    }

    function _scheduleSave(moduleId) {
        var timer = _saveTimers[moduleId]
        if (!timer) {
            timer = saveTimerComponent.createObject(store, { moduleId: moduleId })
            var timers = Object.assign({}, _saveTimers)
            timers[moduleId] = timer
            _saveTimers = timers
        }
        timer.restart()
    }

    function save(moduleId, callback) {
        var timer = _saveTimers[moduleId]
        if (timer)
            timer.stop()
        if (!isDirty(moduleId) || !backendClient) {
            if (callback) callback(null)
            return
        }
        var snapshot = clone(draftFor(moduleId))
        backendClient.draftSave(moduleId, snapshot, function(result) {
            if (result && result.ok) {
                if (JSON.stringify(snapshot) === JSON.stringify(draftFor(moduleId))) {
                    var allDirty = Object.assign({}, dirty)
                    allDirty[moduleId] = false
                    dirty = allDirty
                }
            } else {
                saveFailed(moduleId, result)
            }
            if (callback) callback(result)
        })
    }

    function discard(moduleId, callback) {
        _setDraft(moduleId, {}, false)
        var undoStacks = Object.assign({}, _undoStacks)
        var redoStacks = Object.assign({}, _redoStacks)
        undoStacks[moduleId] = []
        redoStacks[moduleId] = []
        _undoStacks = undoStacks
        _redoStacks = redoStacks
        if (backendClient)
            backendClient.draftDiscard(moduleId, callback)
        else if (callback)
            callback(null)
    }

    function close() {
        var keys = Object.keys(dirty)
        for (var i = 0; i < keys.length; ++i) {
            if (dirty[keys[i]])
                save(keys[i])
        }
    }

    property Shortcut undoShortcut: Shortcut {
        sequence: "Ctrl+Z"
        enabled: store.shortcutsEnabled && store.activeModuleId !== ""
        onActivated: store.undo(store.activeModuleId)
    }

    property Shortcut redoShortcut: Shortcut {
        sequence: "Ctrl+Shift+Z"
        enabled: store.shortcutsEnabled && store.activeModuleId !== ""
        onActivated: store.redo(store.activeModuleId)
    }

    property Component saveTimerComponent: Component {
        Timer {
            property string moduleId: ""
            interval: 750
            repeat: false
            onTriggered: store.save(moduleId)
        }
    }
}
