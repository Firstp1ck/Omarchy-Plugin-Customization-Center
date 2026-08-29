import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui as Ui
import "components" as Modes

FocusScope {
    id: root
    objectName: "modesPage"
    property string moduleId: "modes"
    property var status: null
    property var capabilities: ({})
    property var draft: ({})
    property bool busy: false
    property var backendClient: null
    property string selectedId: ""
    property string viewState: status === null ? "loading" : ((statusData.modes || []).length ? "ready" : "empty")
    property var plan: null
    property var importReview: ({})
    property string shortcutCommand: ""
    property string importText: ""

    signal requestPlan()
    signal requestApply()
    signal requestReset()
    signal requestDraftPatch(var patch)
    signal requestNavigate(string moduleId, var payload)
    signal requestRefresh()

    readonly property var statusData: status && status.data ? status.data : ({})
    readonly property var rows: statusData.modes || []
    readonly property var selectedRow: findRow(selectedId)
    readonly property var activeDraft: root["draft"] && root["draft"].schemaVersion === 1 ? root["draft"] : ({})

    function copy(value) { return JSON.parse(JSON.stringify(value)) }
    function findRow(id) { for (var i=0;i<rows.length;++i) if (rows[i].mode.id === id) return rows[i]; return null }
    function newMode() { return ({ version:1,id:"",name:"",description:"",icon:"",members:({}),triggers:[] }) }
    function editMode(row) {
        var mode = row ? copy(row.mode) : newMode(); selectedId = mode.id
        requestDraftPatch({schemaVersion:1,action:"save",mode:mode,import:null,export:null,expected:{modeDigest:row ? row.digest : null}}); viewState="editing"
    }
    function reviewMode(row) {
        if (!row) return
        selectedId=row.mode.id; requestDraftPatch({schemaVersion:1,action:"apply",mode:copy(row.mode),import:null,export:null,expected:{modeDigest:row.digest}})
        viewState="reviewing"; Qt.callLater(function(){ root.requestPlan() })
    }
    function deleteMode(row) {
        if (!row) return
        requestDraftPatch({schemaVersion:1,action:"delete",mode:{id:row.mode.id},import:null,export:null,expected:{modeDigest:row.digest}}); Qt.callLater(function(){ root.requestPlan() })
    }
    function updateMode(mode) { var next=copy(activeDraft); next.mode=mode; requestDraftPatch(next) }
    function createFromCurrent() {
        if (!backendClient || typeof backendClient.query !== "function") { editMode(null); return }
        backendClient.query(moduleId,"captureable",{selections:({})},function(result){
            var mode=root.newMode(); var values=result && result.data && result.data.members ? result.data.members : ({})
            for (var key in values) if (values[key].available && values[key].section) mode.members[key]=values[key].section
            root.requestDraftPatch({schemaVersion:1,action:"save",mode:mode,import:null,export:null,expected:{modeDigest:null}}); root.viewState="editing"
        })
    }
    function stageImport() {
        try {
            var bundle = JSON.parse(importText)
            requestDraftPatch({schemaVersion:1,action:"import",mode:null,import:{bundle:bundle,resolutions:({})},export:null,expected:{modeDigest:null}})
            importReview=({}); viewState="importing"; Qt.callLater(function(){ root.requestPlan() })
        } catch (error) { viewState="import-error" }
    }
    function exportMode(row) {
        if (!row) return
        requestDraftPatch({schemaVersion:1,action:"export",mode:copy(row.mode),import:null,export:{outputName:row.mode.id+"-export.json"},expected:{modeDigest:row.digest}})
        Qt.callLater(function(){ root.requestPlan() })
    }
    function requestShortcut() {
        if (!selectedRow || !backendClient || typeof backendClient.query !== "function") return
        backendClient.query(moduleId,"shortcut",{modeId:selectedId},function(result){ root.shortcutCommand=result && result.data ? result.data.command || "" : ""; root.viewState="shortcut" })
    }
    function focusFirst() { if (viewState === "editing") editor.focusFirst(); else createButton.forceActiveFocus() }
    function handlePayload(payload) {
        if (!payload || typeof payload.modeId !== "string") return
        var row=findRow(payload.modeId)
        if (!row) { selectedId=payload.modeId; viewState="unknown"; return }
        if (payload.action === "edit") editMode(row); else reviewMode(row)
    }

    onRowsChanged: if (!selectedId && rows.length) selectedId=rows[0].mode.id

    ColumnLayout {
        anchors.fill: parent; spacing: Style.spacing.panelGap
        RowLayout { Layout.fillWidth: true
            Text { Layout.fillWidth: true; text: "Desktop modes"; color: Color.foreground; font.family: Style.font.family; font.pixelSize: Style.font.heading }
            Ui.Button { id:createButton; objectName:"createModeButton"; text:"Create"; enabled:!root.busy; focusable:true; onClicked:root.editMode(null) }
            Ui.Button { objectName:"captureModeButton"; text:"Create from current"; enabled:!root.busy; focusable:true; onClicked:root.createFromCurrent() }
            Ui.Button { objectName:"importModeButton"; text:"Import"; enabled:!root.busy; focusable:true; onClicked:root.viewState="import-entry" }
            Ui.Button { text:"Refresh"; enabled:!root.busy; focusable:true; onClicked:root.requestRefresh() }
        }
        Text { objectName:"stateBanner"; visible:["loading","empty","unknown","stale","failed","recovery_required"].indexOf(root.viewState)>=0; Layout.fillWidth:true; wrapMode:Text.WordWrap
            text: root.viewState === "loading" ? "Loading desktop modes…" : root.viewState === "empty" ? "No desktop modes yet. Create one from selected current settings or start with an empty definition." : root.viewState === "unknown" ? "The requested mode does not exist: " + root.selectedId : root.viewState === "stale" ? "A member changed. Refresh the plan before applying." : root.viewState === "recovery_required" ? "A failed rollback blocks all applies. Open History and run the listed recovery commands." : "The mode transaction failed and rolled back."
            color: root.viewState === "empty" || root.viewState === "loading" ? Color.muted : Color.urgent; font.family:Style.font.family }
        Modes.DriftPanel { Layout.fillWidth:true; report:root.statusData.lastApplied || null }
        RowLayout { Layout.fillWidth:true; Layout.fillHeight:true; visible:["ready","empty","loading"].indexOf(root.viewState)>=0; spacing:Style.spacing.panelGap
            Flickable { Layout.preferredWidth:390; Layout.fillHeight:true; clip:true; contentWidth:width; contentHeight:list.implicitHeight; boundsBehavior:Flickable.StopAtBounds
                ColumnLayout { id:list; width:parent.width
                    Repeater { model:root.rows
                        Modes.ModeCard { required property var modelData; Layout.fillWidth:true; modeRow:modelData; selected:root.selectedId===modelData.mode.id; onSelectedRequested:root.selectedId=modelData.mode.id; onOpenRequested:root.reviewMode(modelData) }
                    }
                }
            }
            ColumnLayout { Layout.fillWidth:true; Layout.fillHeight:true; visible:!!root.selectedRow
                Text { text:root.selectedRow ? root.selectedRow.mode.name : ""; color:Color.foreground; font.family:Style.font.family; font.pixelSize:Style.font.heading }
                Text { Layout.fillWidth:true; text:root.selectedRow ? root.selectedRow.mode.description || "No description" : ""; color:Color.muted; font.family:Style.font.family; wrapMode:Text.WordWrap }
                Repeater { model:root.selectedRow ? root.selectedRow.summaries || [] : []
                    Text { required property string modelData; Layout.fillWidth:true; text:modelData; color:Color.foreground; font.family:Style.font.family; wrapMode:Text.WordWrap }
                }
                RowLayout { Ui.Button { text:"Review"; onClicked:root.reviewMode(root.selectedRow) } Ui.Button { text:"Edit"; onClicked:root.editMode(root.selectedRow) } Ui.Button { text:"Export"; onClicked:root.exportMode(root.selectedRow) } Ui.Button { text:"Shortcut"; onClicked:root.requestShortcut() } Ui.Button { objectName:"deleteModeButton"; text:"Delete " + (root.selectedRow ? root.selectedRow.mode.name : "mode"); onClicked:root.deleteMode(root.selectedRow) } }
            }
        }
        Flickable { Layout.fillWidth:true; Layout.fillHeight:true; visible:root.viewState==="editing"; clip:true; contentWidth:width; contentHeight:editor.implicitHeight
            Modes.ModeEditor { id:editor; width:parent.width; mode:root.activeDraft.mode || root.newMode(); memberCapabilities:root.statusData.memberCapabilities || ({}); onModeEdited:mode=>root.updateMode(mode) }
        }
        Modes.PlanReview { Layout.fillWidth:true; Layout.fillHeight:true; visible:root.viewState==="reviewing"; plan:root.plan; commands:[] }
        ColumnLayout { Layout.fillWidth:true; visible:root.viewState==="import-entry" || root.viewState==="import-error"
            Text { text:"Paste a bounded mode bundle. Staging validates it but never applies it."; color:Color.foreground; font.family:Style.font.family; wrapMode:Text.WordWrap }
            Ui.TextField { Layout.fillWidth:true; placeholderText:"Bundle JSON (maximum 1 MiB)"; text:root.importText; onTextChanged:root.importText=text }
            Text { visible:root.viewState==="import-error"; text:"Bundle JSON could not be parsed."; color:Color.urgent; font.family:Style.font.family }
            Ui.Button { text:"Stage for review"; enabled:root.importText.length>0; onClicked:root.stageImport() }
        }
        Modes.ImportReview { Layout.fillWidth:true; visible:root.viewState==="importing"; review:root.importReview; commandsReviewed:root.activeDraft.import && root.activeDraft.import.resolutions ? root.activeDraft.import.resolutions.commandsReviewed === true : false; onReviewEdited:function(value){ var next=root.copy(root.activeDraft); if(!next.import.resolutions) next.import.resolutions=({}); next.import.resolutions.commandsReviewed=value; root.requestDraftPatch(next) } }
        Modes.ShortcutSheet { Layout.fillWidth:true; visible:root.viewState==="shortcut"; command:root.shortcutCommand; onKeybindingRequested:root.requestNavigate("keybindings",{addBinding:{description:"Mode: "+root.selectedRow.mode.name,action:{type:"exec",command:root.shortcutCommand}}}); onMenuRequested:root.requestNavigate("menu",{addEntry:{parent:"modes",label:root.selectedRow.mode.name,action:root.shortcutCommand}}) }
        RowLayout { visible:["editing","reviewing","importing","shortcut","import-entry","import-error"].indexOf(root.viewState)>=0
            Ui.Button { text:"Back"; onClicked:root.viewState="ready" }
            Ui.Button { objectName:"reviewModeButton"; visible:root.viewState==="editing"; text:"Review save"; enabled:!root.busy; onClicked:root.requestPlan() }
            Ui.Button { objectName:"applyModeButton"; visible:root.viewState==="reviewing" || root.viewState==="importing"; text:root.viewState==="importing" ? "Commit inert import" : "Apply after review"; enabled:!root.busy; onClicked:root.requestApply() }
        }
    }
    Keys.onPressed:function(event){
        if(event.key===Qt.Key_Escape && ["editing","reviewing","importing","shortcut","import-entry","import-error"].indexOf(root.viewState)>=0){root.viewState="ready";event.accepted=true}
        else if(event.key===Qt.Key_Return && (event.modifiers&Qt.ControlModifier) && root.viewState==="ready" && root.selectedRow){root.reviewMode(root.selectedRow);event.accepted=true}
        else if(event.key===Qt.Key_Down && root.rows.length){var at=0;for(var i=0;i<root.rows.length;++i)if(root.rows[i].mode.id===root.selectedId)at=i;root.selectedId=root.rows[Math.min(root.rows.length-1,at+1)].mode.id;event.accepted=true}
        else if(event.key===Qt.Key_Up && root.rows.length){var index=0;for(var j=0;j<root.rows.length;++j)if(root.rows[j].mode.id===root.selectedId)index=j;root.selectedId=root.rows[Math.max(0,index-1)].mode.id;event.accepted=true}
    }
}
