import QtQuick

QtObject {
    id: root
    property var layout: ({ left: [], center: [], right: [] })
    property string grabbedKey: ""
    property var grabSnapshot: null
    signal moved(string key, string section, int index, var layout)
    signal removed(string key, var layout)

    function copy(value) { return JSON.parse(JSON.stringify(value)) }
    function locate(key) {
        var sections = ["left", "center", "right"]
        for (var s = 0; s < sections.length; ++s) {
            var values = layout[sections[s]] || []
            for (var i = 0; i < values.length; ++i) if (values[i].key === key) return ({ section: sections[s], index: i })
        }
        return null
    }
    function move(key, section, index) {
        var next = copy(layout); var source = null; var names = ["left", "center", "right"]
        for (var s = 0; s < names.length; ++s)
            for (var i = 0; i < (next[names[s]] || []).length; ++i)
                if (next[names[s]][i].key === key) source = ({ section: names[s], index: i })
        if (!source || names.indexOf(section) < 0) return
        var item = next[source.section].splice(source.index, 1)[0]
        var target = Math.max(0, Math.min(index, next[section].length))
        next[section].splice(target, 0, item); layout = next; moved(key, section, target, next)
    }
    function remove(key) {
        var location = locate(key); if (!location) return
        var next = copy(layout); next[location.section].splice(location.index, 1); layout = next; removed(key, next)
    }
    function grab(key) { grabbedKey = key; grabSnapshot = copy(layout) }
    function drop() { grabbedKey = ""; grabSnapshot = null }
    function cancel() { if (grabSnapshot) layout = grabSnapshot; grabbedKey = ""; grabSnapshot = null }
}
