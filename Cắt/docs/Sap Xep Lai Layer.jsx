#target photoshop

// ==============================================================================
// SCRIPT: SẮP XẾP CHUẨN XÁC CÁC LAYER ĐANG ĐƯỢC BÔI CHỌN (SELECTED LAYERS ONLY)
// ==============================================================================
// - CHỈ tác động lên đúng các layer bạn bôi chọn trên bảng Layers (không đụng layer khác)
// - Hỏi số ảnh tối đa mỗi cột (Ví dụ: 4 hoặc 5)
// - Tự động giữ nguyên thứ tự từ trên xuống dưới
// - Căn dóng thẳng hàng tuyệt đối thành cột / lưới khít sát nhau
// ==============================================================================

if (app.documents.length === 0) {
    alert("Vui lòng mở file Photoshop trước khi chạy script!");
} else {
    var doc = app.activeDocument;

    // Lưu và đặt đơn vị đo chuẩn Pixels
    var originalRulerUnits = app.preferences.rulerUnits;
    app.preferences.rulerUnits = Units.PIXELS;

    // 1. LẤY DANH SÁCH ID CÁC LAYER ĐANG ĐƯỢC BÔI CHỌN
    var selectedIDs = getSelectedLayerIDs();

    if (!selectedIDs || selectedIDs.length === 0) {
        alert("Bạn chưa chọn layer nào trên bảng Layers!\nHãy giữ Ctrl hoặc Shift để bôi chọn các layer cần sắp xếp.");
        app.preferences.rulerUnits = originalRulerUnits;
    } else if (selectedIDs.length === 1) {
        alert("Bạn mới chỉ chọn 1 layer. Hãy giữ Ctrl hoặc Shift để bôi chọn từ 2 layer trở lên cần xếp hàng!");
        app.preferences.rulerUnits = originalRulerUnits;
    } else {
        // 2. HỎI SỐ ẢNH TỐI ĐA MỖI CỘT
        var maxPerColumn = parseInt(prompt("Số ảnh tối đa mỗi cột:", "5"));
        if (isNaN(maxPerColumn) || maxPerColumn <= 0) {
            app.preferences.rulerUnits = originalRulerUnits;
            exit();
        }

        // 3. LẤY TỌA ĐỘ VÀ KÍCH THƯỚC CỦA TỪNG LAYER ĐƯỢC CHỌN
        var layersInfo = [];
        for (var i = 0; i < selectedIDs.length; i++) {
            var id = selectedIDs[i];
            var bounds = getLayerBoundsByID(id);
            if (bounds) {
                layersInfo.push({
                    id: id,
                    left: bounds[0],
                    top: bounds[1],
                    width: bounds[2] - bounds[0],
                    height: bounds[3] - bounds[1]
                });
            }
        }

        if (layersInfo.length === 0) {
            alert("Không thể đọc thông tin các layer được chọn!");
            app.preferences.rulerUnits = originalRulerUnits;
        } else {
            // 4. SẮP XẾP THỨ TỰ CÁC LAYER TỪ TRÊN XUỐNG DƯỚI (GIỮ NGUYÊN THỨ TỰ ẢNH GỐC)
            layersInfo.sort(function (a, b) {
                return a.top - b.top;
            });

            // 5. TÍNH KÍCH THƯỚC Ô VÀ ĐIỂM BẮT ĐẦU (GÓC TRÊN TRÁI CỦA NHÓM ẢNH)
            var itemWidth = layersInfo[0].width;
            var itemHeight = layersInfo[0].height;

            var minX = layersInfo[0].left;
            var minY = layersInfo[0].top;

            for (var j = 1; j < layersInfo.length; j++) {
                if (layersInfo[j].left < minX) minX = layersInfo[j].left;
                if (layersInfo[j].top < minY) minY = layersInfo[j].top;
            }

            // 6. DỊCH CHUYỂN TỪNG LAYER ĐƯỢC CHỌN VÀO ĐÚNG VỊ TRÍ CỘT / LƯỚI
            for (var k = 0; k < layersInfo.length; k++) {
                var item = layersInfo[k];

                var colIndex = Math.floor(k / maxPerColumn);
                var rowIndex = k % maxPerColumn;

                var targetX = minX + (colIndex * itemWidth);
                var targetY = minY + (rowIndex * itemHeight);

                var dx = targetX - item.left;
                var dy = targetY - item.top;

                translateLayerByID(item.id, dx, dy);
            }

            // 7. BÔI CHỌN LẠI TOÀN BỘ CÁC LAYER ĐÃ SẮP XẾP ĐỂ NGƯỜI DÙNG DỄ QUẢN LÝ
            selectMultipleLayersByIDs(selectedIDs);

            app.preferences.rulerUnits = originalRulerUnits;
            alert("🎉 Đã sắp xếp " + layersInfo.length + " layer được chọn thành cột ngay ngắn (Tối đa " + maxPerColumn + " ảnh/cột)!");
        }
    }
}

// ==============================================================================
// HÀM ACTION MANAGER: LẤY DANH SÁCH ID CỦA CÁC LAYER ĐƯỢC CHỌN
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

    // Nếu chỉ có 1 layer đang được chọn
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
// HÀM ACTION MANAGER: LẤY BOUNDS CỦA LAYER THEO ID
// ==============================================================================
function getLayerBoundsByID(layerID) {
    try {
        var ref = new ActionReference();
        ref.putIdentifier(charIDToTypeID("Lyr "), layerID);
        var desc = executeActionGet(ref);
        var boundsDesc = desc.getObjectValue(stringIDToTypeID("bounds"));

        var left = boundsDesc.getUnitDoubleValue(stringIDToTypeID("left"));
        var top = boundsDesc.getUnitDoubleValue(stringIDToTypeID("top"));
        var right = boundsDesc.getUnitDoubleValue(stringIDToTypeID("right"));
        var bottom = boundsDesc.getUnitDoubleValue(stringIDToTypeID("bottom"));

        return [left, top, right, bottom];
    } catch (e) {
        return null;
    }
}

// ==============================================================================
// HÀM ACTION MANAGER: DỊCH CHUYỂN LAYER THEO ID
// ==============================================================================
function translateLayerByID(layerID, dx, dy) {
    if (dx === 0 && dy === 0) return;

    try {
        // Chọn layer cần dịch chuyển
        var ref = new ActionReference();
        ref.putIdentifier(charIDToTypeID("Lyr "), layerID);
        var desc = new ActionDescriptor();
        desc.putReference(charIDToTypeID("null"), ref);
        executeAction(charIDToTypeID("slct"), desc, DialogModes.NO);

        // Dịch chuyển
        var moveDesc = new ActionDescriptor();
        var moveRef = new ActionReference();
        moveRef.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
        moveDesc.putReference(charIDToTypeID("null"), moveRef);

        var offsetDesc = new ActionDescriptor();
        offsetDesc.putUnitDouble(charIDToTypeID("Hrzn"), charIDToTypeID("#Pxl"), dx);
        offsetDesc.putUnitDouble(charIDToTypeID("Vrtc"), charIDToTypeID("#Pxl"), dy);
        moveDesc.putObject(charIDToTypeID("T   "), charIDToTypeID("Ofst"), offsetDesc);

        executeAction(charIDToTypeID("move"), moveDesc, DialogModes.NO);
    } catch (e) { }
}

// ==============================================================================
// HÀM ACTION MANAGER: BÔI CHỌN NHIỀU LAYER THEO DANH SÁCH ID
// ==============================================================================
function selectMultipleLayersByIDs(ids) {
    if (!ids || ids.length === 0) return;
    try {
        // Chọn layer đầu tiên
        var ref = new ActionReference();
        ref.putIdentifier(charIDToTypeID("Lyr "), ids[0]);
        var desc = new ActionDescriptor();
        desc.putReference(charIDToTypeID("null"), ref);
        executeAction(charIDToTypeID("slct"), desc, DialogModes.NO);

        // Thêm các layer còn lại vào vùng chọn
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
