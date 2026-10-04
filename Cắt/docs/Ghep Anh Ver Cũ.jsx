#target photoshop

var files = File.openDialog("Chọn các ảnh để ghép", "*.*", true);
if (!files || files.length === 0) {
    alert("Bạn chưa chọn ảnh!");
    exit();
}

var maxPerColumn = parseInt(prompt("Số ảnh tối đa mỗi cột:", "5"));
if (isNaN(maxPerColumn) || maxPerColumn <= 0) {
    alert("Giá trị không hợp lệ!");
    exit();
}

// Lưu và đặt đơn vị đo chuẩn Pixels
var originalRulerUnits = app.preferences.rulerUnits;
app.preferences.rulerUnits = Units.PIXELS;

// TỰ ĐỘNG LẤY CHIỀU RỘNG VÀ CHIỀU CAO TỪ ẢNH ĐẦU TIÊN
var tempDoc = app.open(files[0]);
var targetWidth = Number(tempDoc.width.value);
var targetHeight = Number(tempDoc.height.value);
tempDoc.close(SaveOptions.DONOTSAVECHANGES);

var totalImages = files.length;
var totalColumns = Math.ceil(totalImages / maxPerColumn);

// 🔥 TÍNH SỐ HÀNG THỰC TẾ
var realRows = Math.min(maxPerColumn, totalImages);

// CANVAS
var canvasWidth = totalColumns * targetWidth;
var canvasHeight = realRows * targetHeight;

var newDoc = app.documents.add(
    canvasWidth,
    canvasHeight,
    72,
    "Merged_Fixed",
    NewDocumentMode.RGB,
    DocumentFill.WHITE
);

// PLACE FUNCTION
function placeFile(file) {
    var desc = new ActionDescriptor();
    desc.putPath(charIDToTypeID("null"), file);
    desc.putEnumerated(
        charIDToTypeID("FTcs"),
        charIDToTypeID("QCSt"),
        charIDToTypeID("Qcsa")
    );
    executeAction(charIDToTypeID("Plc "), desc, DialogModes.NO);
}

// HÀM TẠO LAYER CHỈNH MÀU HUE/SATURATION
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

// HÀM TẠO LAYER CHỈNH MÀU BRIGHTNESS/CONTRAST
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

// GHÉP
for (var i = 0; i < totalImages; i++) {

    placeFile(files[i]);
    var layer = newDoc.activeLayer;

    var bounds = layer.bounds;
    var w = bounds[2] - bounds[0];
    var h = bounds[3] - bounds[1];

    layer.resize((targetWidth / w) * 100, (targetHeight / h) * 100);

    var columnIndex = totalColumns - 1 - Math.floor(i / maxPerColumn);
    var rowIndex = maxPerColumn - 1 - (i % maxPerColumn);

    var x = columnIndex * targetWidth;
    var y = rowIndex * targetHeight;

    layer.translate(x - layer.bounds[0], y - layer.bounds[1]);
}

// 🔥 TỰ ĐỘNG TẠO 2 LAYER CHỈNH MÀU Ở VỊ TRÍ CAO NHẤT (TOP)
if (newDoc.layers.length > 0) {
    newDoc.activeLayer = newDoc.layers[0];
}

// 1. Layer Hue/Saturation (Hue: +4, Saturation: +20, Lightness: 0)
addHueSaturationLayer(4, 20, 0);

// 2. Layer Brightness/Contrast (Brightness: -3, Contrast: 5, Use Legacy: false)
addBrightnessContrastLayer(-3, 5, false);

// Khôi phục đơn vị đo ban đầu
app.preferences.rulerUnits = originalRulerUnits;

alert("Xong!");
