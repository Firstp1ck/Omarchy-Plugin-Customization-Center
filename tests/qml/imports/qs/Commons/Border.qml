pragma Singleton
import QtQuick
QtObject {
    function spec(color, width) { return { color: color, widths: { top: width, right: width, bottom: width, left: width } } }
    function localOrSurfaceSpec(section, token, localColor, defaultColor, width) { return spec(localColor, width) }
    function controlSpec(state, foreground, accent) { return spec(foreground, 1) }
}
