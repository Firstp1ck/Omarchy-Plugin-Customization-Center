import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui
import "components" as Plugins

FocusScope {
    id: root
    objectName: "pluginsPage"
    property string moduleId: "plugins"
    property var status: null
    property var capabilities: ({})
    property var draft: ({})
    property bool busy: false
    property var backendClient: null
    property string selectedId: ""
    property string selectedTab: "overview"
    property string filter: "all"
    property var validationResult: null
    property bool actionMenuOpen: false

    signal requestPlan()
    signal requestApply()
    signal requestReset()
    signal requestDraftPatch(var patch)
    signal requestNavigate(string moduleId, var payload)
    signal requestRefresh()
    signal requestAbandon(string transactionId)

    readonly property var statusData: status && status.data ? status.data : ({})
    readonly property var rows: statusData.rows || []
    readonly property var activeDraft: root["draft"] && root["draft"].schemaVersion === 1 ? root["draft"] : baseDraft()
    readonly property string pageState: status === null ? "loading"
        : !statusData.shell || statusData.shell.available !== true ? "shell-unavailable"
        : statusData.pendingHandoffs && statusData.pendingHandoffs.length ? "pending-handoff"
        : activeDraft.baseRevision !== status.revision ? "stale"
        : statusData.diagnostics && statusData.diagnostics.warnings && statusData.diagnostics.warnings.length ? "catalog-degraded"
        : "ready"
    property var selectedRow: null
    readonly property var filteredRows: filterRows()

    function copy(value) { return JSON.parse(JSON.stringify(value)) }
    function baseDraft() { return ({ schemaVersion: 1, module: "plugins", baseRevision: status ? status.revision : "", changes: [] }) }
    function findRow(id) { for (var i = 0; i < rows.length; ++i) if (rows[i].id === id) return rows[i]; return null }
    function hasCapability(row, name) {
        if (!row) return false
        for (var i = 0; i < (row.capabilities || []).length; ++i) {
            var value = row.capabilities[i]
            if (value === name || (typeof value === "object" && value.name === name)) return true
        }
        return false
    }
    function filterRows() {
        var needle = search.text.toLowerCase(); var result = []
        for (var i = 0; i < rows.length; ++i) {
            var row = rows[i]; var text = (row.id + " " + row.name + " " + (row.description || "")).toLowerCase()
            if (needle && text.indexOf(needle) < 0) continue
            if (filter === "omarchy" && !row.firstParty) continue
            if (filter === "installed" && row.firstParty) continue
            if (filter === "clones" && !(row.origin && row.origin.class === "user-clone")) continue
            if (filter === "on-bar" && !(row.instances && row.instances.length)) continue
            if (filter === "switched-off" && row.state.enabled) continue
            if (filter === "bars" && (row.kinds || []).indexOf("bar") < 0) continue
            if (filter === "settings" && (!row.settings || row.settings.support === "none") && !(row.settings && row.settings.extension)) continue
            if (filter === "diagnostics" && !(row.diagnostics && row.diagnostics.length)) continue
            result.push(row)
        }
        return result
    }
    function selectRow(id) { selectedId = id; selectedRow = findRow(id); validationResult = null }
    function setToggle(row) {
        if (!row || row.ownership !== "plugins") return
        var kind = row.state.enabled ? "disable" : "enable"
        if (!hasCapability(row, kind)) return
        requestDraftPatch({ schemaVersion: 1, module: "plugins", baseRevision: status.revision,
            changes: [{ kind: kind, pluginId: row.id, closesCenter: row.self === true }] })
    }
    function lifecycle(action, row, edit) {
        if (action !== "add" && !row) return
        var change = { kind: "lifecycle", action: action, closesCenter: row ? row.self === true : false }
        if (row) change.pluginId = row.id
        if (action === "clone") change.edit = edit === true
        requestDraftPatch({ schemaVersion: 1, module: "plugins", baseRevision: status.revision, changes: [change] })
        Qt.callLater(function() { root.requestPlan() })
    }
    function deepLink(row) {
        if (!row || row.ownership !== "bar") return
        if ((row.kinds || []).indexOf("bar") >= 0) requestNavigate("bar", { selectBar: row.id })
        else if ((row.instances || []).length) requestNavigate("bar", { select: { section: row.instances[0].section, index: row.instances[0].index } })
        else requestNavigate("bar", { addWidget: row.id })
    }
    function runValidation(pluginId) {
        if (!backendClient || typeof backendClient.query !== "function") return
        backendClient.query(moduleId, "validate", { id: pluginId }, function(result) {
            root.validationResult = result && result.data ? result.data : ({ exit: 1, stderr: "Validation query failed" })
        })
    }
    function focusFirst() { search.forceActiveFocus() }
    function handlePayload(payload) {
        if (!payload) return
        if (typeof payload.select === "string" && findRow(payload.select)) selectRow(payload.select)
        if (["overview", "placement", "settings", "diagnostics"].indexOf(payload.tab) >= 0) selectedTab = payload.tab
        if (payload.action === "add") lifecycle("add", null, false)
    }

    onRowsChanged: {
        if (!selectedId && rows.length) selectedId = rows[0].id
        selectedRow = findRow(selectedId)
    }
    onSelectedIdChanged: selectedRow = findRow(selectedId)

    ColumnLayout {
        anchors.fill: parent
        spacing: Style.spacing.panelGap
        RowLayout {
            Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: "Plugins"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading }
            Text { objectName: "shellStateChip"; text: root.statusData.shell && root.statusData.shell.available ? "Shell connected" : "Shell unavailable"; color: root.statusData.shell && root.statusData.shell.available ? Color.foreground : Color.urgent; font.family: Style.font.family }
            Ui.Button { text: "Refresh"; focusable: true; enabled: !root.busy; onClicked: root.requestRefresh() }
            Ui.Button { objectName: "addPluginButton"; text: "Add"; focusable: true; enabled: !root.busy && root.statusData.shell && root.statusData.shell.available; onClicked: root.lifecycle("add", null, false) }
        }
        Text {
            Layout.fillWidth: true
            visible: root.statusData.shell && root.statusData.shell.barFallback === true
            text: "Configured bar " + root.statusData.shell.configuredBar + " is not running; the shell is using " + root.statusData.shell.runningBar + ". Open it in the bar editor."
            wrapMode: Text.WordWrap; color: Color.urgent; font.family: Style.font.family
            TapHandler { onTapped: root.requestNavigate("bar", { selectBar: root.statusData.shell.configuredBar }) }
        }
        Text {
            objectName: "pageStateBanner"
            Layout.fillWidth: true; visible: root.pageState !== "ready" && root.pageState !== "pending-handoff"
            text: root.pageState === "loading" ? "Loading plugin catalog…"
                : root.pageState === "shell-unavailable" ? "omarchy-shell is unavailable. Static catalog entries are diagnostics only and no plugin action is enabled."
                : root.pageState === "catalog-degraded" ? "Runtime rows are available, but omarchy-plugin-catalog enrichment failed. Origin and settings metadata may be unknown."
                : root.pageState === "stale" ? "The plugin catalog changed. Reload or compare before applying this draft."
                : root.pageState === "rollback-failed" ? "Rollback failed. Stop applying changes and follow the transaction recovery commands." : root.pageState
            wrapMode: Text.WordWrap; color: Color.urgent; font.family: Style.font.family
        }
        Plugins.HandoffStrip { Layout.fillWidth: true; handoffs: root.statusData.pendingHandoffs || []; onAbandonRequested: transactionId => root.requestAbandon(transactionId) }
        RowLayout {
            Layout.fillWidth: true
            Ui.TextField { id: search; objectName: "pluginSearch"; Layout.fillWidth: true; placeholderText: "Search id, name, or description" }
            Repeater {
                model: [["all", "All"], ["omarchy", "Omarchy"], ["installed", "Installed"], ["clones", "Clones"], ["on-bar", "On bar"], ["switched-off", "Switched off"], ["bars", "Bars"], ["settings", "Has settings"], ["diagnostics", "Diagnostics"]]
                Ui.Button { required property var modelData; text: modelData[1]; selected: root.filter === modelData[0]; focusable: true; onClicked: root.filter = modelData[0] }
            }
        }
        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: Style.spacing.panelGap
            Flickable {
                Layout.preferredWidth: root.width >= 900 ? 390 : root.width
                Layout.fillHeight: true
                clip: true
                contentWidth: width
                contentHeight: pluginList.implicitHeight
                boundsBehavior: Flickable.StopAtBounds
                ColumnLayout {
                    id: pluginList
                    width: parent.width
                    Repeater {
                        id: rowRepeater
                        model: root.filteredRows
                        Plugins.PluginRow {
                            required property var modelData
                            Layout.fillWidth: true
                            row: modelData
                            selected: root.selectedId === modelData.id
                            onSelectedRequested: root.selectRow(modelData.id)
                            onActionMenuRequested: { root.selectRow(modelData.id); root.actionMenuOpen = true }
                        }
                    }
                }
            }
            ColumnLayout {
                visible: root.width >= 900
                Layout.fillWidth: true; Layout.fillHeight: true; spacing: Style.spacing.md
                RowLayout {
                    Repeater {
                        model: [["overview", "Overview"], ["placement", "Placement"], ["settings", "Settings"], ["diagnostics", "Diagnostics"]]
                        Ui.Button { required property var modelData; text: modelData[1]; selected: root.selectedTab === modelData[0]; focusable: true; onClicked: root.selectedTab = modelData[0] }
                    }
                }
                Plugins.DetailOverview { Layout.fillWidth: true; visible: root.selectedTab === "overview"; row: root.selectedRow }
                Plugins.DetailPlacement { Layout.fillWidth: true; visible: root.selectedTab === "placement"; row: root.selectedRow; onNavigateRequested: payload => root.requestNavigate("bar", payload) }
                Plugins.DetailSettings { Layout.fillWidth: true; visible: root.selectedTab === "settings"; row: root.selectedRow; onNavigateRequested: payload => root.requestNavigate("bar", payload) }
                Plugins.DetailDiagnostics { Layout.fillWidth: true; visible: root.selectedTab === "diagnostics"; row: root.selectedRow; validation: root.validationResult; canValidate: root.hasCapability(root.selectedRow, "validate"); onValidateRequested: pluginId => root.runValidation(pluginId) }
                RowLayout {
                    visible: !!root.selectedRow
                    Ui.Button { objectName: "enableButton"; text: root.selectedRow && root.selectedRow.state && root.selectedRow.state.enabled ? "Disable" : "Enable"; visible: !!root.selectedRow && root.selectedRow.ownership === "plugins"; enabled: !root.busy && !!root.selectedRow && !!root.selectedRow.state && root.hasCapability(root.selectedRow, root.selectedRow.state.enabled ? "disable" : "enable"); focusable: true; onClicked: root.setToggle(root.selectedRow) }
                    Ui.Button { text: "Edit in bar editor"; visible: root.selectedRow && root.selectedRow.ownership === "bar"; focusable: true; onClicked: root.deepLink(root.selectedRow) }
                    Ui.Button { text: "Update"; visible: root.hasCapability(root.selectedRow, "update"); focusable: true; onClicked: root.lifecycle("update", root.selectedRow, false) }
                    Ui.Button { text: "Remove"; visible: root.hasCapability(root.selectedRow, "remove"); focusable: true; onClicked: root.lifecycle("remove", root.selectedRow, false) }
                    Ui.Button { text: "Clone"; visible: root.hasCapability(root.selectedRow, "clone"); focusable: true; onClicked: root.lifecycle("clone", root.selectedRow, false) }
                    Ui.Button { text: "Clone and edit"; visible: root.hasCapability(root.selectedRow, "clone-edit"); focusable: true; onClicked: root.lifecycle("clone", root.selectedRow, true) }
                }
            }
        }
    }
    Rectangle {
        objectName: "rowActionMenu"
        visible: root.actionMenuOpen && !!root.selectedRow
        z: 20
        width: 230
        implicitHeight: menuContent.implicitHeight + Style.spacing.md * 2
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        color: Color.background
        border.color: Color.muted
        border.width: 1
        radius: Style.cornerRadius
        ColumnLayout {
            id: menuContent
            anchors.fill: parent
            anchors.margins: Style.spacing.md
            Ui.Button { Layout.fillWidth: true; text: root.selectedRow && root.selectedRow.state && root.selectedRow.state.enabled ? "Disable" : "Enable"; visible: !!root.selectedRow && root.selectedRow.ownership === "plugins"; enabled: !root.busy && !!root.selectedRow.state && root.hasCapability(root.selectedRow, root.selectedRow.state.enabled ? "disable" : "enable"); focusable: true; onClicked: { root.actionMenuOpen = false; root.setToggle(root.selectedRow) } }
            Ui.Button { Layout.fillWidth: true; text: "Edit in bar editor"; visible: !!root.selectedRow && root.selectedRow.ownership === "bar"; focusable: true; onClicked: { root.actionMenuOpen = false; root.deepLink(root.selectedRow) } }
            Ui.Button { Layout.fillWidth: true; text: "Update"; visible: root.hasCapability(root.selectedRow, "update"); focusable: true; onClicked: { root.actionMenuOpen = false; root.lifecycle("update", root.selectedRow, false) } }
            Ui.Button { Layout.fillWidth: true; text: "Remove"; visible: root.hasCapability(root.selectedRow, "remove"); focusable: true; onClicked: { root.actionMenuOpen = false; root.lifecycle("remove", root.selectedRow, false) } }
            Ui.Button { Layout.fillWidth: true; text: "Clone"; visible: root.hasCapability(root.selectedRow, "clone"); focusable: true; onClicked: { root.actionMenuOpen = false; root.lifecycle("clone", root.selectedRow, false) } }
            Ui.Button { Layout.fillWidth: true; text: "Clone and edit"; visible: root.hasCapability(root.selectedRow, "clone-edit"); focusable: true; onClicked: { root.actionMenuOpen = false; root.lifecycle("clone", root.selectedRow, true) } }
            Ui.Button { Layout.fillWidth: true; text: "Close"; focusable: true; onClicked: root.actionMenuOpen = false }
        }
    }
    Keys.onPressed: function(event) {
        if (event.key === Qt.Key_Down && root.filteredRows.length) {
            var at = 0; for (var i = 0; i < root.filteredRows.length; ++i) if (root.filteredRows[i].id === root.selectedId) at = i
            root.selectedId = root.filteredRows[Math.min(root.filteredRows.length - 1, at + 1)].id; event.accepted = true
        } else if (event.key === Qt.Key_Up && root.filteredRows.length) {
            var index = 0; for (var j = 0; j < root.filteredRows.length; ++j) if (root.filteredRows[j].id === root.selectedId) index = j
            root.selectedId = root.filteredRows[Math.max(0, index - 1)].id; event.accepted = true
        }
    }
}
