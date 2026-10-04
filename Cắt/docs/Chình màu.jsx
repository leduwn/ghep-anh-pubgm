#target photoshop

// ==============================================================================
// SCRIPT PHOTOSHOP: TỰ ĐỘNG TẠO 2 LAYER CHỈNH MÀU TRÊN CÙNG
// ==============================================================================
// 1. Layer Hue/Saturation 1: Hue +4, Saturation +20, Lightness 0
// 2. Layer Brightness/Contrast 1: Brightness -3, Contrast +5, Use Legacy: false
// ==============================================================================

if (app.documents.length === 0) {
    alert("Vui lòng mở ít nhất một tài liệu ảnh trong Photoshop trước khi chạy script!");
} else {
    var doc = app.activeDocument;

    // Chọn layer trên cùng hiện tại để layer mới sinh ra nằm ở vị trí cao nhất (Top)
    if (doc.layers.length > 0) {
        doc.activeLayer = doc.layers[0];
    }

    // 1. TẠO LAYER HUE/SATURATION (Hue: +4, Saturation: +20, Lightness: 0)
    addHueSaturationLayer(4, 20, 0);

    // 2. TẠO LAYER BRIGHTNESS/CONTRAST (Brightness: -3, Contrast: 5, Use Legacy: false)
    addBrightnessContrastLayer(-3, 5, false);

    alert("Đã tự động tạo 2 Layer chỉnh màu thành công!");
}

// ==============================================================================
// CÁC HÀM XỬ LÝ ACTION MANAGER
// ==============================================================================

// Hàm tạo Layer Hue/Saturation
function addHueSaturationLayer(hue, sat, lightness) {
    try {
        var desc = new ActionDescriptor();
        var ref = new ActionReference();
        ref.putClass(stringIDToTypeID("adjustmentLayer"));
        desc.putReference(stringIDToTypeID("null"), ref);

        var descUsing = new ActionDescriptor();
        var descType = new ActionDescriptor();

        var descPreset = new ActionDescriptor();
        descPreset.putInteger(stringIDToTypeID("hue"), hue);
        descPreset.putInteger(stringIDToTypeID("saturation"), sat);
        descPreset.putInteger(stringIDToTypeID("lightness"), lightness);

        var list = new ActionList();
        list.putObject(stringIDToTypeID("hueSatAdjustmentV2"), descPreset);
        descType.putList(stringIDToTypeID("adjustment"), list);

        descUsing.putObject(stringIDToTypeID("type"), stringIDToTypeID("hueSaturation"), descType);
        desc.putObject(stringIDToTypeID("using"), stringIDToTypeID("adjustmentLayer"), descUsing);

        executeAction(stringIDToTypeID("make"), desc, DialogModes.NO);
    } catch (e) {
        try {
            var desc2 = new ActionDescriptor();
            var ref2 = new ActionReference();
            ref2.putClass(charIDToTypeID("AdjL"));
            desc2.putReference(charIDToTypeID("null"), ref2);

            var descUsing2 = new ActionDescriptor();
            var descType2 = new ActionDescriptor();
            var descPreset2 = new ActionDescriptor();
            descPreset2.putInteger(charIDToTypeID("H   "), hue);
            descPreset2.putInteger(charIDToTypeID("Strt"), sat);
            descPreset2.putInteger(charIDToTypeID("Lght"), lightness);

            var list2 = new ActionList();
            list2.putObject(charIDToTypeID("Hst2"), descPreset2);
            descType2.putList(charIDToTypeID("Adjs"), list2);

            descUsing2.putObject(charIDToTypeID("Type"), charIDToTypeID("HStr"), descType2);
            desc2.putObject(charIDToTypeID("Usng"), charIDToTypeID("AdjL"), descUsing2);
            executeAction(charIDToTypeID("Mk  "), desc2, DialogModes.NO);
        } catch (err) { }
    }
}

// Hàm tạo Layer Brightness/Contrast
function addBrightnessContrastLayer(brightness, contrast, useLegacy) {
    try {
        var desc = new ActionDescriptor();
        var ref = new ActionReference();
        ref.putClass(stringIDToTypeID("adjustmentLayer"));
        desc.putReference(stringIDToTypeID("null"), ref);

        var descUsing = new ActionDescriptor();
        var descType = new ActionDescriptor();
        descType.putInteger(stringIDToTypeID("brightness"), brightness);
        descType.putInteger(stringIDToTypeID("contrast"), contrast);
        descType.putBoolean(stringIDToTypeID("useLegacy"), useLegacy ? true : false);

        descUsing.putObject(stringIDToTypeID("type"), stringIDToTypeID("brightnessEvent"), descType);
        desc.putObject(stringIDToTypeID("using"), stringIDToTypeID("adjustmentLayer"), descUsing);

        executeAction(stringIDToTypeID("make"), desc, DialogModes.NO);
    } catch (e) {
        try {
            var desc2 = new ActionDescriptor();
            var ref2 = new ActionReference();
            ref2.putClass(charIDToTypeID("AdjL"));
            desc2.putReference(charIDToTypeID("null"), ref2);

            var descUsing2 = new ActionDescriptor();
            var descType2 = new ActionDescriptor();
            descType2.putInteger(charIDToTypeID("Brgh"), brightness);
            descType2.putInteger(charIDToTypeID("Cntr"), contrast);
            descType2.putBoolean(stringIDToTypeID("useLegacy"), useLegacy ? true : false);

            descUsing2.putObject(charIDToTypeID("Type"), charIDToTypeID("BrgC"), descType2);
            desc2.putObject(charIDToTypeID("Usng"), charIDToTypeID("AdjL"), descUsing2);
            executeAction(charIDToTypeID("Mk  "), desc2, DialogModes.NO);
        } catch (err) { }
    }
}
