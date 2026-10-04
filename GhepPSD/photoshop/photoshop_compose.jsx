#target photoshop

(function () {
    function readUtf8(filePath) {
        var file = new File(filePath);
        file.encoding = "UTF8";
        if (!file.open("r")) throw new Error("Không đọc được file job: " + filePath);
        var value = file.read();
        file.close();
        return value;
    }

    function writeUtf8(filePath, value) {
        var file = new File(filePath);
        file.encoding = "UTF8";
        if (!file.open("w")) return;
        file.write(value);
        file.close();
    }

    function parseJson(value) {
        if (typeof JSON !== "undefined" && JSON.parse) return JSON.parse(value);
        return eval("(" + value + ")");
    }

    function px(value) {
        try { return Number(value.as("px")); } catch (e) { return Number(value); }
    }

    function boundsPx(layer) {
        var b = layer.bounds;
        return [px(b[0]), px(b[1]), px(b[2]), px(b[3])];
    }

    function placeSmartObject(doc, placement, group) {
        var source = new File(placement.path);
        if (!source.exists) throw new Error("Thiếu ảnh: " + placement.path);

        app.activeDocument = doc;
        var desc = new ActionDescriptor();
        desc.putPath(charIDToTypeID("null"), source);
        desc.putEnumerated(
            charIDToTypeID("FTcs"),
            charIDToTypeID("QCSt"),
            charIDToTypeID("Qcsa")
        );
        executeAction(charIDToTypeID("Plc "), desc, DialogModes.NO);

        var layer = doc.activeLayer;
        layer.name = placement.name;
        var b = boundsPx(layer);
        var currentWidth = Math.max(1, b[2] - b[0]);
        var currentHeight = Math.max(1, b[3] - b[1]);
        layer.resize(
            placement.width / currentWidth * 100,
            placement.height / currentHeight * 100,
            AnchorPosition.TOPLEFT
        );
        b = boundsPx(layer);
        layer.translate(placement.x - b[0], placement.y - b[1]);
        // Trang phục và từng ô kho nằm ở root để Move Tool chọn trực tiếp
        // đúng một ảnh, thay vì Photoshop chọn cả cụm lớn.
        if (!placement.direct_select && group) {
            layer.move(group, ElementPlacement.INSIDE);
        }
        return layer;
    }

    function addWatermark(doc, group, job) {
        if (!job.watermark || !job.watermark.enabled) return;
        app.activeDocument = doc;
        var layer = doc.artLayers.add();
        layer.kind = LayerKind.TEXT;
        layer.name = "ACC_WATERMARK_EDIT_ME";
        layer.textItem.contents = "Z" + job.account_id;
        layer.textItem.size = UnitValue(job.watermark.font_size, "px");
        try { layer.textItem.font = "Arial-BoldMT"; } catch (e) { }
        layer.textItem.justification = Justification.RIGHT;
        var white = new SolidColor();
        white.rgb.red = 255;
        white.rgb.green = 255;
        white.rgb.blue = 255;
        layer.textItem.color = white;
        layer.textItem.position = [
            UnitValue(job.canvas.width - job.watermark.margin, "px"),
            UnitValue(job.canvas.height - job.watermark.margin, "px")
        ];
        if (group) layer.move(group, ElementPlacement.INSIDE);
    }

    function copyLabelLibrary(doc, group, libraryPath) {
        if (!libraryPath) return;
        var sourceFile = new File(libraryPath);
        if (!sourceFile.exists) return;

        var sourceDoc = app.open(sourceFile);
        var sourceWidth = px(sourceDoc.width);
        var sourceHeight = px(sourceDoc.height);
        var copied = 0;
        for (var i = sourceDoc.layers.length - 1; i >= 0; i--) {
            var sourceLayer = sourceDoc.layers[i];
            try {
                var b = boundsPx(sourceLayer);
                var width = b[2] - b[0];
                var height = b[3] - b[1];
                if (width >= sourceWidth * 0.9 && height >= sourceHeight * 0.9) continue;
                // Nhân thẳng vào group đích. Nhân vào document rồi move sẽ để
                // lại layer rác ở root trên một số bản Photoshop.
                sourceLayer.duplicate(group, ElementPlacement.INSIDE);
                copied++;
            } catch (ignoreLayer) { }
        }
        sourceDoc.close(SaveOptions.DONOTSAVECHANGES);
        app.activeDocument = doc;
        group.name = "90_LABEL_LIBRARY_HIDDEN_" + copied + "_LAYERS";
        hideLayer(doc, group);
    }

    function hideLayer(doc, layer) {
        app.activeDocument = doc;
        doc.activeLayer = layer;
        try { layer.visible = false; } catch (ignoreVisible) { }
        // Một số bản Photoshop bật lại group khi vừa nhận layer từ document
        // khác. Action Manager đảm bảo trạng thái mắt được tắt trước khi save.
        try {
            var hideDescriptor = new ActionDescriptor();
            var hideList = new ActionList();
            var hideReference = new ActionReference();
            hideReference.putEnumerated(
                charIDToTypeID("Lyr "),
                charIDToTypeID("Ordn"),
                charIDToTypeID("Trgt")
            );
            hideList.putReference(hideReference);
            hideDescriptor.putList(charIDToTypeID("null"), hideList);
            executeAction(charIDToTypeID("Hd  "), hideDescriptor, DialogModes.NO);
        } catch (ignoreHide) { }
    }

    function saveOutputs(doc, job) {
        var psdFile = new File(job.output_psd);
        var psdOptions = new PhotoshopSaveOptions();
        psdOptions.layers = true;
        psdOptions.embedColorProfile = true;
        psdOptions.maximizeCompatibility = true;
        // Lưu PSD làm tài liệu chính để file đang mở trong Photoshop chính là
        // file người dùng sẽ tiếp tục chỉnh sửa.
        doc.saveAs(psdFile, psdOptions, false, Extension.LOWERCASE);

        var pngFile = new File(job.output_png);
        var pngOptions = new PNGSaveOptions();
        pngOptions.compression = 6;
        pngOptions.interlaced = false;
        doc.saveAs(pngFile, pngOptions, true, Extension.LOWERCASE);
    }

    var oldUnits = app.preferences.rulerUnits;
    var job = null;
    try {
        if (typeof AUTO_GHEP_JOB_PATH === "undefined") {
            throw new Error("Thiếu AUTO_GHEP_JOB_PATH trong file chạy.");
        }
        job = parseJson(readUtf8(AUTO_GHEP_JOB_PATH));
        app.preferences.rulerUnits = Units.PIXELS;

        var oldBackground = app.backgroundColor;
        var black = new SolidColor();
        black.rgb.red = 0;
        black.rgb.green = 0;
        black.rgb.blue = 0;
        app.backgroundColor = black;
        var doc = app.documents.add(
            job.canvas.width,
            job.canvas.height,
            72,
            "GHEP_ACC_" + job.account_id,
            NewDocumentMode.RGB,
            DocumentFill.BACKGROUNDCOLOR
        );
        app.backgroundColor = oldBackground;

        var groups = {};
        for (var g = job.groups.length - 1; g >= 0; g--) {
            var group = doc.layerSets.add();
            group.name = job.groups[g];
            groups[job.groups[g]] = group;
        }

        for (var i = 0; i < job.placements.length; i++) {
            var placement = job.placements[i];
            placeSmartObject(doc, placement, groups[placement.group]);
        }

        addWatermark(doc, null, job);
        if (job.label_library_path) {
            copyLabelLibrary(doc, groups["90_LABEL_LIBRARY"], job.label_library_path);
        }
        if (groups["21_VEHICLE_LABELS"]) {
            groups["21_VEHICLE_LABELS"].move(doc, ElementPlacement.PLACEATBEGINNING);
        }
        if (groups["31_OUTFIT_LABELS"]) {
            groups["31_OUTFIT_LABELS"].move(doc, ElementPlacement.PLACEATBEGINNING);
        }

        app.activeDocument = doc;
        saveOutputs(doc, job);
        writeUtf8(job.completion_path, '{"ok":true}');
    } catch (error) {
        if (job && job.completion_path) {
            var detail = String(error) + (error.line ? " (line " + error.line + ")" : "");
            var safeMessage = detail.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
            writeUtf8(job.completion_path, '{"ok":false,"error":"' + safeMessage + '"}');
        }
        throw error;
    } finally {
        app.preferences.rulerUnits = oldUnits;
    }
}());
