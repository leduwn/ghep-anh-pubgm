#target photoshop

// ==============================================================================
// SCRIPT: TỰ ĐỘNG THÊM STROKE (VIỀN VÀNG) CHO TỪNG LAYER ĐƯỢC CHỌN (1-CLICK)
// ==============================================================================
// - Bôi đen (chọn) các layer trên bảng Layers và chạy script
// - Script tự động duyệt qua TỪNG LAYER và gán hiệu ứng Stroke:
//     * Màu viền  : Vàng tươi (#FFF000 / RGB: 255, 240, 0)
//     * Kiểu viền : Inside (Nằm gọn bên trong viền ảnh, khít sát mép)
//     * Độ dày    : 5 px
//     * Độ mờ đục : 100%
// - Giữ nguyên các Layer Style khác đang có (Drop Shadow, Color Overlay,...)
// ==============================================================================

if (app.documents.length === 0) {
    alert("Vui lòng mở file Photoshop trước khi chạy script!");
} else {
    var doc = app.activeDocument;
    var originalRulerUnits = app.preferences.rulerUnits;
    app.preferences.rulerUnits = Units.PIXELS;

    var selectedIDs = getSelectedLayerIDs();

    if (!selectedIDs || selectedIDs.length === 0) {
        alert("Bạn chưa chọn layer nào trên bảng Layers!\nHãy giữ Ctrl hoặc Shift để bôi chọn các layer cần thêm viền vàng.");
        app.preferences.rulerUnits = originalRulerUnits;
    } else {
        var strokeSize = 5; // Độ dày viền Inside (px)
        var r = 255, g = 240, b = 0; // Màu vàng tươi
        var successCount = 0;
        var failedCount = 0;

        for (var i = 0; i < selectedIDs.length; i++) {
            var layerID = selectedIDs[i];
            try {
                selectLayerByID(layerID);
                setLayerStroke(strokeSize, r, g, b);
                successCount++;
            } catch (err) {
                failedCount++;
            }
        }

        // Bôi chọn lại các layer ban đầu
        selectMultipleLayersByIDs(selectedIDs);
        app.preferences.rulerUnits = originalRulerUnits;

        var message = "Đã thêm Stroke vàng Inside 5 px cho " + successCount + " layer.";
        if (failedCount > 0) {
            message += "\nBỏ qua " + failedCount + " layer không hỗ trợ hiệu ứng.";
        }
        alert(message);
    }
}

// ==============================================================================
// HÀM CHỌN LAYER THEO ID
// ==============================================================================
function selectLayerByID(layerID) {
    var ref = new ActionReference();
    ref.putIdentifier(charIDToTypeID("Lyr "), layerID);
    var desc = new ActionDescriptor();
    desc.putReference(charIDToTypeID("null"), ref);
    desc.putBoolean(charIDToTypeID("MkVs"), false);
    executeAction(charIDToTypeID("slct"), desc, DialogModes.NO);
}

// ==============================================================================
// HÀM TẠO STROKE CHO LAYER ĐANG ĐƯỢC CHỌN (ACTION MANAGER CHUẨN)
// ==============================================================================
function setLayerStroke(size, r, g, b) {
    var effectsKey = charIDToTypeID("Lefx");
    var desc = new ActionDescriptor();
    var ref = new ActionReference();
    ref.putProperty(charIDToTypeID("Prpr"), effectsKey);
    ref.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
    desc.putReference(charIDToTypeID("null"), ref);

    // Đọc Layer Style hiện tại để không xóa Drop Shadow/Overlay/Glow đã có.
    var lefxDesc = getCurrentLayerEffects();
    if (!lefxDesc.hasKey(charIDToTypeID("Scl "))) {
        lefxDesc.putUnitDouble(charIDToTypeID("Scl "), charIDToTypeID("#Prc"), 100.0);
    }

    var strokeDesc = new ActionDescriptor();
    strokeDesc.putBoolean(charIDToTypeID("enab"), true);
    strokeDesc.putBoolean(stringIDToTypeID("present"), true);
    strokeDesc.putBoolean(stringIDToTypeID("showInDialog"), true);
    strokeDesc.putEnumerated(charIDToTypeID("Styl"), charIDToTypeID("FStl"), charIDToTypeID("InsF")); // Inside
    strokeDesc.putEnumerated(charIDToTypeID("PntT"), charIDToTypeID("FrFl"), charIDToTypeID("SClr")); // Solid Color
    strokeDesc.putEnumerated(charIDToTypeID("Md  "), charIDToTypeID("BlnM"), charIDToTypeID("Nrml")); // Normal
    strokeDesc.putUnitDouble(charIDToTypeID("Opct"), charIDToTypeID("#Prc"), 100.0);
    strokeDesc.putUnitDouble(charIDToTypeID("Sz  "), charIDToTypeID("#Pxl"), size);

    var colorDesc = new ActionDescriptor();
    colorDesc.putDouble(charIDToTypeID("Rd  "), r);
    colorDesc.putDouble(charIDToTypeID("Grn "), g);
    colorDesc.putDouble(charIDToTypeID("Bl  "), b);
    strokeDesc.putObject(charIDToTypeID("Clr "), charIDToTypeID("RGBC"), colorDesc);

    lefxDesc.putObject(charIDToTypeID("FrFX"), charIDToTypeID("FrFX"), strokeDesc);
    desc.putObject(charIDToTypeID("T   "), effectsKey, lefxDesc);

    executeAction(charIDToTypeID("setd"), desc, DialogModes.NO);
}

// ==============================================================================
// HÀM ĐỌC LAYER STYLE HIỆN TẠI (ĐỂ GIỮ NGUYÊN CÁC HIỆU ỨNG KHÁC)
// ==============================================================================
function getCurrentLayerEffects() {
    var effectsKey = charIDToTypeID("Lefx");
    try {
        var ref = new ActionReference();
        ref.putProperty(charIDToTypeID("Prpr"), effectsKey);
        ref.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
        var layerDesc = executeActionGet(ref);
        if (layerDesc.hasKey(effectsKey)) {
            return layerDesc.getObjectValue(effectsKey);
        }
    } catch (e) { }
    return new ActionDescriptor();
}

// ==============================================================================
// HÀM LẤY DANH SÁCH ID CỦA CÁC LAYER ĐƯỢC CHỌN
// ==============================================================================
function getSelectedLayerIDs() {
    var ids = [];
    try {
        var ref = new ActionReference();
        ref.putEnumerated(charIDToTypeID("Dcmn"), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
        var desc = executeActionGet(ref);

        if (desc.hasKey(stringIDToTypeID("targetLayersIDs"))) {
            var list = desc.getList(stringIDToTypeID("targetLayersIDs"));
            for (var i = 0; i < list.count; i++) {
                try {
                    ids.push(list.getReference(i).getIdentifier());
                } catch (e1) {
                    try {
                        ids.push(list.getInteger(i));
                    } catch (e2) { }
                }
            }
        }
    } catch (e) { }

    if (ids.length === 0) {
        try {
            var ref2 = new ActionReference();
            ref2.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
            var desc2 = executeActionGet(ref2);
            ids.push(desc2.getInteger(charIDToTypeID("LyrI")));
        } catch (e) { }
    }
    return ids;
}

// ==============================================================================
// HÀM BÔI CHỌN NHIỀU LAYER THEO DANH SÁCH ID
// ==============================================================================
function selectMultipleLayersByIDs(ids) {
    if (!ids || ids.length === 0) return;
    try {
        var ref = new ActionReference();
        ref.putIdentifier(charIDToTypeID("Lyr "), ids[0]);
        var desc = new ActionDescriptor();
        desc.putReference(charIDToTypeID("null"), ref);
        executeAction(charIDToTypeID("slct"), desc, DialogModes.NO);

        for (var i = 1; i < ids.length; i++) {
            var refAdd = new ActionReference();
            refAdd.putIdentifier(charIDToTypeID("Lyr "), ids[i]);
            var descAdd = new ActionDescriptor();
            descAdd.putReference(charIDToTypeID("null"), refAdd);
            descAdd.putEnumerated(stringIDToTypeID("selectionModifier"), stringIDToTypeID("selectionModifierType"), stringIDToTypeID("addToSelection"));
            executeAction(charIDToTypeID("slct"), descAdd, DialogModes.NO);
        }
    } catch (e) { }
}
