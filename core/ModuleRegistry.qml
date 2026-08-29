import QtQuick

Item {
    id: registry

    property var backendClient: null
    property var draftStore: null
    property var modules: []
    property string selectedModuleId: ""
    property var statusByModule: ({})
    property var busyByModule: ({})
    property bool loading: false
    property bool opened: false
    property string errorCode: ""
    property string errorMessage: ""
    property var pendingPayload: null
    property var _statusPoll: null
    readonly property var selectedModule: moduleById(selectedModuleId)
    readonly property alias pageItem: pageLoader.item

    signal moduleSelected(string moduleId)
    signal pageReady(string moduleId, var page)
    signal requestPlan(string moduleId)
    signal requestApply(string moduleId)
    signal requestReset(string moduleId)

    function moduleById(moduleId) {
        for (var i = 0; i < modules.length; ++i) {
            if (modules[i].id === moduleId)
                return modules[i]
        }
        return null
    }

    function open(payload) {
        pendingPayload = payload || ({})
        if (opened) {
            routePayload(pendingPayload)
            return
        }
        opened = true
        loading = true
        errorCode = ""
        backendClient.modules(function(result) {
            loading = false
            if (!result || !result.ok) {
                var error = result && result.errors && result.errors.length ? result.errors[0] : ({ code: "runtime_unavailable", message: "Could not load modules" })
                errorCode = error.code
                errorMessage = error.message
                return
            }
            var rows = result.data && (result.data.modules || result.data.items) ? (result.data.modules || result.data.items) : []
            rows = rows.slice().filter(function(row) { return row.hidden !== true })
            rows.sort(function(a, b) { return Number(a.navOrder || 0) - Number(b.navOrder || 0) })
            modules = rows
            var wanted = pendingPayload && (pendingPayload.module || pendingPayload.page)
            select(wanted && moduleById(wanted) ? wanted : (rows.length ? rows[0].id : ""), pendingPayload)
        })
    }

    function close() {
        stopStatusPolling()
        opened = false
        pageLoader.source = ""
        modules = []
        selectedModuleId = ""
        statusByModule = ({})
        busyByModule = ({})
    }

    function select(moduleId, payload) {
        var target = moduleById(moduleId)
        if (!target)
            return false
        pendingPayload = payload || ({})
        stopStatusPolling()
        selectedModuleId = moduleId
        if (draftStore) {
            draftStore.activeModuleId = moduleId
            draftStore.load(moduleId, function() { registry.updatePageProperties() })
        }
        pageLoader.source = target.pageUrl || target.page || ""
        moduleSelected(moduleId)
        refreshStatus(moduleId)
        return true
    }

    function routePayload(payload) {
        var target = payload && (payload.module || payload.page)
        if (target && target !== selectedModuleId) {
            select(target, payload)
        } else if (pageLoader.item && typeof pageLoader.item.handlePayload === "function") {
            pageLoader.item.handlePayload(payload || ({}))
        } else {
            pendingPayload = payload || ({})
        }
    }

    function refreshStatus(moduleId, callback) {
        if (!moduleId)
            return
        setBusy(moduleId, true)
        backendClient.status(moduleId, function(result) {
            setBusy(moduleId, false)
            acceptStatus(moduleId, result)
            if (callback) callback(result)
        })
    }

    function pageHandlesPendingHandoffs() {
        return pageLoader.item && pageLoader.item.handlesPendingHandoffs === true
    }

    function acceptStatus(moduleId, result) {
        if (result && result.ok) {
            var all = Object.assign({}, statusByModule)
            all[moduleId] = result.data && result.data.status ? result.data.status : result.data
            statusByModule = all
            updatePageProperties()
            var pending = result.data && result.data.pendingHandoffs ? result.data.pendingHandoffs : []
            if (moduleId === selectedModuleId && pending.length > 0 && !pageHandlesPendingHandoffs())
                startStatusPolling(moduleId)
            else if (moduleId === selectedModuleId)
                stopStatusPolling()
        }
    }

    function startStatusPolling(moduleId) {
        if (_statusPoll || !backendClient)
            return
        _statusPoll = backendClient.pollStatus(moduleId, 2000, function(result) {
            registry.acceptStatus(moduleId, result)
        })
    }

    function stopStatusPolling() {
        if (_statusPoll && backendClient)
            backendClient.stopPolling(_statusPoll)
        _statusPoll = null
    }

    function setBusy(moduleId, value) {
        var all = Object.assign({}, busyByModule)
        all[moduleId] = value
        busyByModule = all
        updatePageProperties()
    }

    function updatePageProperties() {
        var page = pageLoader.item
        if (!page)
            return
        page.moduleId = selectedModuleId
        if ("backendClient" in page)
            page.backendClient = backendClient
        page.status = statusByModule[selectedModuleId] || null
        page.capabilities = selectedModule && selectedModule.capabilities ? selectedModule.capabilities : ({})
        page.draft = draftStore ? draftStore.draftFor(selectedModuleId) : ({})
        page.busy = busyByModule[selectedModuleId] === true
    }

    Loader {
        id: pageLoader
        anchors.fill: parent
        asynchronous: false
        onLoaded: {
            registry.updatePageProperties()
            if (item && typeof item.handlePayload === "function")
                item.handlePayload(registry.pendingPayload || ({}))
            if (item && typeof item.focusFirst === "function")
                Qt.callLater(item.focusFirst)
            registry.pageReady(registry.selectedModuleId, item)
        }
    }

    Connections {
        target: pageLoader.item
        ignoreUnknownSignals: true
        function onRequestPlan() { registry.requestPlan(registry.selectedModuleId) }
        function onRequestApply() { registry.requestApply(registry.selectedModuleId) }
        function onRequestReset() { registry.requestReset(registry.selectedModuleId) }
        function onRequestDraftPatch(patch) {
            if (registry.draftStore)
                registry.draftStore.applyPatch(registry.selectedModuleId, patch)
        }
        function onRequestNavigate(moduleId, payload) { registry.select(moduleId, payload) }
    }

    Connections {
        target: draftStore
        ignoreUnknownSignals: true
        function onDraftUpdated(moduleId) {
            if (moduleId === registry.selectedModuleId)
                registry.updatePageProperties()
        }
    }
}
