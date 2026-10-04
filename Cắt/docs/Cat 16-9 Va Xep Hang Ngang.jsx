#target photoshop

// ==============================================================================
// SCRIPT: CẮT 2 BÊN CHÍNH GIỮA (CHUẨN FORM MẪU) & GHÉP KHÍT HÀNG NGANG
// ==============================================================================
// 1. Áp dụng cho các layer đang được BÔI CHỌN trên bảng Layers.
// 2. Tự động cắt bỏ 2 bên trái/phải theo đúng độ dài mẫu gửi (mặc định 70px mỗi bên).
// 3. Tự động dóng hàng ngang và xếp SÁT KHÍT NHAU 100% KHÔNG BỊ HỞ KHOẢNG TRỐNG.
// ==============================================================================

if (app.documents.length === 0) {
    alert("Vui lòng mở file Photoshop trước khi chạy script!");
} else {
    var doc = app.activeDocument;

    // Lưu và đặt đơn vị đo chuẩn Pixels
    var originalRulerUnits = app.preferences.rulerUnits;
    app.preferences.rulerUnits = Units.PIXELS;

    // 1. LẤY DANH SÁCH LAYER ĐANG ĐƯỢC BÔI CHỌN
    var selectedLayers = getSelectedLayersList(doc);

    if (!selectedLayers || selectedLayers.length === 0) {
        alert("Bạn chưa chọn layer nào trên bảng Layers!\nHãy giữ Ctrl hoặc Shift để bôi chọn các layer cần cắt và ghép.");
        app.preferences.rulerUnits = originalRulerUnits;
    } else {
        // 2. HỎI SỐ PIXEL CẮT BỎ MỖI BÊN (Mặc định 70px)
        var cutInput = prompt("Số pixel cắt bỏ MỖI BÊN trái/phải (px):", "70");
        if (cutInput === null) {
            app.preferences.rulerUnits = originalRulerUnits;
            exit();
        }

        var cutPixels = parseInt(cutInput);
        if (isNaN(cutPixels) || cutPixels < 0) {
            cutPixels = 70;
        }

        // 3. SẮP XẾP DANH SÁCH THEO THỨ TỰ TỪ TRÁI SANG PHẢI (GIỮ ĐÚNG THỨ TỰ ẢNH)
        selectedLayers.sort(function (a, b) {
            return Number(a.bounds[0]) - Number(b.bounds[0]);
        });

        // 4. TỌA ĐỘ GỐC BẮT ĐẦU (Góc trên trái của ảnh đầu tiên)
        var startX = Number(selectedLayers[0].bounds[0]);
        var startY = Number(selectedLayers[0].bounds[1]);

        if (startX < 0) startX = 0;
        if (startY < 0) startY = 0;

        var newCroppedLayers = [];
        var processedWidths = [];

        // 5. CẮT BỎ 2 BÊN BẰNG LAYER VIA COPY (TRIỆT TIÊU HOÀN TOÀN VIỀN TRONG SUỐT)
        for (var i = 0; i < selectedLayers.length; i++) {
            var oldLayer = selectedLayers[i];
            doc.activeLayer = oldLayer;

            // Rasterize nếu là Smart Object
            try {
                oldLayer.rasterize(RasterizeType.ENTIRELAYER);
            } catch (e) { }

            var b = oldLayer.bounds;
            var curX = Number(b[0]);
            var curY = Number(b[1]);
            var curW = Number(b[2] - b[0]);
            var curH = Number(b[3] - b[1]);

            // Tính toán vùng cắt ở chính giữa
            var actualCut = cutPixels;
            if (actualCut * 2 >= curW) {
                actualCut = Math.round(curW * 0.05);
            }

            var x1 = curX + actualCut;
            var y1 = curY;
            var x2 = curX + curW - actualCut;
            var y2 = curY + curH;
            var croppedW = x2 - x1;

            // Tạo vùng chọn hình chữ nhật chính xác
            var selRegion = [
                [x1, y1],
                [x2, y1],
                [x2, y2],
                [x1, y2]
            ];
            doc.selection.select(selRegion, SelectionType.REPLACE, 0, false);

            // Nhân bản vùng chọn thành layer mới sạch viền (Layer Via Copy - Ctrl+J)
            executeAction(charIDToTypeID("CpTL"), undefined, DialogModes.NO);
            var newLayer = doc.activeLayer;

            // Xóa layer cũ chưa cắt
            oldLayer.remove();

            newCroppedLayers.push(newLayer);
            processedWidths.push(croppedW);

            doc.selection.deselect();
        }

        // 6. XẾP CÁC LAYER SÁT KHÍT NHAU 100% THEO HÀNG NGANG
        var currentPlacementX = startX;

        for (var j = 0; j < newCroppedLayers.length; j++) {
            var lyr = newCroppedLayers[j];
            var curB = lyr.bounds;
            var currentLayerX = Number(curB[0]);
            var currentLayerY = Number(curB[1]);

            var dx = currentPlacementX - currentLayerX;
            var dy = startY - currentLayerY;

            lyr.translate(dx, dy);

            // Đẩy vị trí X của ảnh tiếp theo sát khít ảnh này
            currentPlacementX += processedWidths[j];
        }

        // 7. TỰ ĐỘNG MỞ RỘNG CANVAS NẾU ẢNH TRÀN KHUNG
        if (currentPlacementX > doc.width.value) {
            doc.resizeCanvas(currentPlacementX + startX, doc.height.value, AnchorPosition.TOPLEFT);
        }

        // 8. BÔI CHỌN LẠI CÁC LAYER ĐÃ GHÉP
        selectMultipleLayers(newCroppedLayers);

        app.preferences.rulerUnits = originalRulerUnits;
        alert("🎉 Đã cắt 2 bên và ghép khít sát " + newCroppedLayers.length + " ảnh theo hàng ngang thành công!");
    }
}

// ==============================================================================
// HÀM ACTION MANAGER: LẤY DANH SÁCH LAYER ĐƯỢC BÔI CHỌN
// ==============================================================================
function getSelectedLayersList(doc) {
    var result = [];
    try {
        var ref = new ActionReference();
        ref.putEnumerated(charIDToTypeID("Dcmn"), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
        var desc = executeActionGet(ref);

        if (desc.hasKey(stringIDToTypeID("targetLayersIDs"))) {
            var list = desc.getList(stringIDToTypeID("targetLayersIDs"));
            for (var i = 0; i < list.count; i++) {
                var layerID = 0;
                try {
                    layerID = list.getReference(i).getIdentifier();
                } catch (e1) {
                    try {
                        layerID = list.getInteger(i);
                    } catch (e2) { }
                }

                if (layerID > 0) {
                    var l = findLayerByID(doc, layerID);
                    if (l) result.push(l);
                }
            }
        }
    } catch (e) { }

    if (result.length === 0 && doc.activeLayer) {
        result.push(doc.activeLayer);
    }

    return result;
}

function findLayerByID(container, id) {
    for (var i = 0; i < container.layers.length; i++) {
        var lyr = container.layers[i];
        try {
            if (lyr.id === id) return lyr;
        } catch (e) { }

        if (lyr.typename === "LayerSet") {
            var found = findLayerByID(lyr, id);
            if (found) return found;
        }
    }
    return null;
}

function selectMultipleLayers(layers) {
    if (!layers || layers.length === 0) return;
    try {
        doc.activeLayer = layers[0];
        for (var i = 1; i < layers.length; i++) {
            var ref = new ActionReference();
            ref.putIdentifier(charIDToTypeID("Lyr "), layers[i].id);
            var desc = new ActionDescriptor();
            desc.putReference(charIDToTypeID("null"), ref);
            desc.putEnumerated(stringIDToTypeID("selectionModifier"), stringIDToTypeID("selectionModifierType"), stringIDToTypeID("addToSelection"));
            executeAction(charIDToTypeID("slct"), desc, DialogModes.NO);
        }
    } catch (e) { }
}
