#target photoshop

// AUTO_GHEP_LABEL_SOURCE and AUTO_GHEP_LABEL_DIR are set by the wrapper.
(function () {
    if (typeof AUTO_GHEP_LABEL_SOURCE === "undefined" ||
        typeof AUTO_GHEP_LABEL_DIR === "undefined") {
        throw new Error("Thiếu đường dẫn kho nhãn trang phục.");
    }
    var sourceFile = new File(AUTO_GHEP_LABEL_SOURCE);
    var targetDir = new Folder(AUTO_GHEP_LABEL_DIR);
    if (!sourceFile.exists) throw new Error("Thiếu kho nhãn: " + sourceFile.fsName);
    if (!targetDir.exists) targetDir.create();

    function px(value) {
        try { return Number(value.as("px")); } catch (e) { return Number(value); }
    }
    function bounds(layer) {
        var b = layer.bounds;
        return [px(b[0]), px(b[1]), px(b[2]), px(b[3])];
    }
    function moveTopLeft(layer, x, y) {
        var b = bounds(layer);
        layer.translate(x - b[0], y - b[1]);
    }
    function saveTransparent(doc, name, right, bottom) {
        app.activeDocument = doc;
        doc.crop([0, 0, Math.ceil(right + 8), Math.ceil(bottom + 8)]);
        var options = new PNGSaveOptions();
        options.compression = 6;
        doc.saveAs(new File(targetDir.fsName + "/" + name + ".png"),
                   options, true, Extension.LOWERCASE);
        doc.close(SaveOptions.DONOTSAVECHANGES);
    }

    var oldUnits = app.preferences.rulerUnits;
    var source = null;
    try {
        app.preferences.rulerUnits = Units.PIXELS;
        source = app.open(sourceFile);
        var digitSource = source.artLayers.getByName("3");
        var starSource = source.artLayers.getByName("Layer 35 copy 9");
        var vipSource = source.artLayers.getByName("Layer 25 copy 10");

        for (var number = 1; number <= 7; number++) {
            var doc = app.documents.add(320, 150, 72, "outfit_" + number + "star",
                                        NewDocumentMode.RGB, DocumentFill.TRANSPARENT);
            app.activeDocument = source;
            var digit = digitSource.duplicate(doc, ElementPlacement.PLACEATBEGINNING);
            app.activeDocument = doc;
            digit.textItem.contents = String(number);
            moveTopLeft(digit, 8, 8);
            var digitBounds = bounds(digit);
            app.activeDocument = source;
            var star = starSource.duplicate(doc, ElementPlacement.PLACEATBEGINNING);
            app.activeDocument = doc;
            moveTopLeft(star, digitBounds[2] - 6, digitBounds[3] - (bounds(star)[3] - bounds(star)[1]));
            var starBounds = bounds(star);
            saveTransparent(doc, "star_" + number,
                            Math.max(digitBounds[2], starBounds[2]),
                            Math.max(digitBounds[3], starBounds[3]));
        }

        var vipDoc = app.documents.add(260, 100, 72, "outfit_vip",
                                       NewDocumentMode.RGB, DocumentFill.TRANSPARENT);
        app.activeDocument = source;
        var vip = vipSource.duplicate(vipDoc, ElementPlacement.PLACEATBEGINNING);
        app.activeDocument = vipDoc;
        moveTopLeft(vip, 8, 8);
        var vipBounds = bounds(vip);
        saveTransparent(vipDoc, "vip", vipBounds[2], vipBounds[3]);
        source.close(SaveOptions.DONOTSAVECHANGES);
        source = null;
    } finally {
        if (source) source.close(SaveOptions.DONOTSAVECHANGES);
        app.preferences.rulerUnits = oldUnits;
    }
}());
