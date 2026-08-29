import QtQuick
import QtTest
import "../../" as Defaults

TestCase {
    name: "DefaultsPage"
    when: windowShown
    width: 900
    height: 700

    Component { id: pageComponent; Defaults.Page {} }

    function test_contract_and_loading_state() {
        var page = createTemporaryObject(pageComponent, this, { width: 900, height: 700 })
        verify(page !== null)
        compare(page.moduleId, "defaults")
        compare(page.categories.length, 4)
        page.focusFirst()
    }
}
