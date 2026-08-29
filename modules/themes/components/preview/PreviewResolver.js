.pragma library

function resolve(draft, machineOverride, options) {
    var palette = draft && draft.palette ? JSON.parse(JSON.stringify(draft.palette)) : ({})
    palette.urgent = palette.red
    var roles = { foreground: palette.foreground, text: palette.foreground, accent: palette.accent,
                  urgent: palette.red, muted: palette.muted, background: palette.background,
                  transparent: "#00000000" }
    return { palette: palette, roles: roles, sections: draft.sections || ({}),
             machineOverride: machineOverride || ({}), masked: Object.keys(machineOverride || ({})).sort() }
}
