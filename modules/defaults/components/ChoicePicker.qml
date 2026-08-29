import QtQuick
import qs.Commons
import qs.Ui as Ui

FocusScope {
    id: root
    property var choices: []
    property string selector: ""
    property string currentChoice: ""
    property var detailsChoice: null
    signal choicePicked(var choice)

    implicitHeight: pickerColumn.implicitHeight

    function filteredChoices() {
        var result = []
        var needle = search.text.toLowerCase()
        for (var i = 0; i < choices.length; ++i) {
            var item = choices[i]
            if (!needle || String(item.label).toLowerCase().indexOf(needle) >= 0 || String(item.id).toLowerCase().indexOf(needle) >= 0)
                result.push(item)
        }
        return result
    }
    function focusFirst() { search.forceActiveFocus() }
    function focusRow(index) {
        var row = choiceRows.itemAt(index)
        if (row) row.forceActiveFocus()
    }

    Column {
        id: pickerColumn
        width: parent.width
        spacing: (Style.spacing.sm || Style.space(6))
        Ui.TextField {
            id: search
            objectName: "choiceSearch"
            width: parent.width
            enabled: root.enabled
            placeholderText: "Search choices"
            Keys.onEscapePressed: text = ""
            Keys.onDownPressed: root.focusRow(0)
        }
        Repeater {
            id: choiceRows
            model: root.filteredChoices()
            delegate: Row {
                id: row
                required property var modelData
                required property int index
                width: pickerColumn.width
                spacing: (Style.spacing.sm || Style.space(6))
                function forceActiveFocus() { chooseButton.forceActiveFocus() }
                Ui.Button {
                    id: chooseButton
                    objectName: "choiceAction_" + row.modelData.id
                    width: row.width - detailsButton.width - row.spacing
                    text: row.modelData.label + " · " + row.modelData.state + " · argv: " + root.selector + " " + row.modelData.id
                    leftAlign: true
                    bordered: true
                    focusable: true
                    selected: root.currentChoice === row.modelData.id
                    enabled: root.enabled
                    onClicked: root.choicePicked(row.modelData)
                    Keys.onDownPressed: root.focusRow(Math.min(choiceRows.count - 1, row.index + 1))
                    Keys.onUpPressed: row.index === 0 ? search.forceActiveFocus() : root.focusRow(row.index - 1)
                }
                Ui.Button {
                    id: detailsButton
                    objectName: "detailsAction_" + row.modelData.id
                    text: root.detailsChoice && root.detailsChoice.id === row.modelData.id ? "Hide details" : "Details"
                    bordered: true
                    focusable: true
                    enabled: root.enabled
                    onClicked: root.detailsChoice = root.detailsChoice && root.detailsChoice.id === row.modelData.id ? null : row.modelData
                }
            }
        }
        ChoiceDetails { width: parent.width; choice: root.detailsChoice; selector: root.selector }
    }
}
