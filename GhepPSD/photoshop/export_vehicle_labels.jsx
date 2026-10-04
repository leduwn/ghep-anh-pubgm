#target photoshop

// AUTO_GHEP_VEHICLE_SOURCE and AUTO_GHEP_VEHICLE_DIR are set by the wrapper.
(function () {
    if (typeof AUTO_GHEP_VEHICLE_SOURCE === "undefined" ||
        typeof AUTO_GHEP_VEHICLE_DIR === "undefined") {
        throw new Error("Thiếu đường dẫn kho chữ vé xe.");
    }
    var sourceFile = new File(AUTO_GHEP_VEHICLE_SOURCE);
    var targetDir = new Folder(AUTO_GHEP_VEHICLE_DIR);
    if (!sourceFile.exists) throw new Error("Thiếu kho chữ: " + sourceFile.fsName);
    if (!targetDir.exists) targetDir.create();

    function px(value) {
        try { return Number(value.as("px")); } catch (e) { return Number(value); }
    }
    function bounds(layer) {
        var b = layer.bounds;
        return [px(b[0]), px(b[1]), px(b[2]), px(b[3])];
    }
    function exportText(source, template, key, value) {
        var doc = app.documents.add(900, 170, 72, "vehicle_" + key,
                                    NewDocumentMode.RGB, DocumentFill.TRANSPARENT);
        app.activeDocument = source;
        var layer = template.duplicate(doc, ElementPlacement.PLACEATBEGINNING);
        app.activeDocument = doc;
        layer.textItem.contents = value;
        var b = bounds(layer);
        layer.translate(8 - b[0], 8 - b[1]);
        b = bounds(layer);
        doc.crop([0, 0, Math.ceil(b[2] + 8), Math.ceil(b[3] + 8)]);
        var options = new PNGSaveOptions();
        options.compression = 6;
        doc.saveAs(new File(targetDir.fsName + "/" + key + ".png"),
                   options, true, Extension.LOWERCASE);
        doc.close(SaveOptions.DONOTSAVECHANGES);
    }

    var labels = [
        ["ticket_3", "3VÉ"],
        ["ticket_3_2cmt", "3VÉ - 2CMT"],
        ["ticket_1_2cmt", "1VÉ - 2CMT"],
        ["ticket_1_2c", "1VÉ - 2C"],
        ["ticket_1_4c", "1VÉ - 4C"],
        ["ticket_3_2c", "3VÉ - 2C"],
        ["ticket_3_4c", "3VÉ - 4C"],
        ["ticket_1_mt", "1VÉ - MT"],
        ["ticket_3_mt", "3VÉ - MT"]
    ];
    var oldUnits = app.preferences.rulerUnits;
    var source = null;
    try {
        app.preferences.rulerUnits = Units.PIXELS;
        source = app.open(sourceFile);
        var template = source.artLayers.getByName("1 VÉ  -  4C");
        for (var i = 0; i < labels.length; i++) {
            exportText(source, template, labels[i][0], labels[i][1]);
        }
        source.close(SaveOptions.DONOTSAVECHANGES);
        source = null;
    } finally {
        if (source) source.close(SaveOptions.DONOTSAVECHANGES);
        app.preferences.rulerUnits = oldUnits;
    }
}());
