import QtQuick
import QtTest
import "../.." as Modes
TestCase {
 name: "ModesPage"
 Component { id: pageComponent; Modes.Page {} }
 function test_payload_unknown_is_safe() { var page=createTemporaryObject(pageComponent,this); verify(page!==null); page.status={data:{modes:[]}}; page.handlePayload({modeId:"missing",action:"review"}); compare(page.viewState,"unknown") }
 function test_selection_never_applies() { var page=createTemporaryObject(pageComponent,this); verify(page!==null); var count=0; page.requestApply.connect(function(){count++}); page.selectedId="x"; compare(count,0) }
 function test_close_state_does_not_confirm() { var page=createTemporaryObject(pageComponent,this); verify(page!==null); page.viewState="awaiting_confirmation"; compare(page.viewState,"awaiting_confirmation") }
}
