#target photoshop

// ==============================================================================
// SCRIPT: SẮP XẾP XE THEO MÀU NỀN (ĐỎ -> TÍM -> KHÁC) THÀNH 1 CỘT DUY NHẤT
// ==============================================================================
// - Áp dụng CHUYÊN BIỆT cho các layer thẻ xe PUBG Mobile đang được bôi chọn
// - Tự động nhận diện màu nền từng thẻ xe:
//     * ƯU TIÊN 1 (Trên cùng) : Thẻ xe nền ĐỎ (Mythic / Thần thoại)
//     * ƯU TIÊN 2 (Ở giữa)    : Thẻ xe nền TÍM (Upgrade / Nâng cấp)
//     * ƯU TIÊN 3 (Dưới cùng) : Thẻ xe nền KHÁC / XÁM / TỐI (Spy x Family, Event,...)
// - Tự động xếp tất cả thành 1 CỘT DUY NHẤT từ trên xuống dưới
// - Căn dóng thẳng hàng tuyệt đối, khít sát nhau 100%
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
        alert("Bạn chưa chọn layer nào trên bảng Layers!\nHãy giữ Ctrl hoặc Shift để bôi chọn các layer thẻ xe cần sắp xếp.");
        app.preferences.rulerUnits = originalRulerUnits;
    } else if (selectedIDs.length === 1) {
        alert("Bạn mới chỉ chọn 1 layer. Hãy bôi chọn từ 2 layer trở lên để sắp xếp theo màu!");
        app.preferences.rulerUnits = originalRulerUnits;
    } else {
        // 2. LƯU TRẠNG THÁI HIỂN THỊ BAN ĐẦU CỦA CÁC LAYER
        var originalVisibilities = {};
        for (var v = 0; v < selectedIDs.length; v++) {
            originalVisibilities[selectedIDs[v]] = getLayerVisibilityByID(selectedIDs[v]);
        }

        // 3. ĐỌC TỌA ĐỘ VÀ NHẬN DIỆN MÀU NỀN CỦA TỪNG LAYER
        var layersInfo = [];

        for (var i = 0; i < selectedIDs.length; i++) {
            var id = selectedIDs[i];
            var bounds = getLayerBoundsByID(id);
            if (bounds) {
                // Tạm thời chỉ bật layer hiện tại để lấy mẫu màu chính xác tuyệt đối
                for (var j = 0; j < selectedIDs.length; j++) {
                    setLayerVisibilityByID(selectedIDs[j], selectedIDs[j] === id);
                }

                // Nhận diện màu nền (1: Đỏ, 2: Tím, 3: Khác)
                var colorRank = detectLayerColorType(bounds, doc);

                layersInfo.push({
                    id: id,
                    left: bounds[0],
                    top: bounds[1],
                    width: bounds[2] - bounds[0],
                    height: bounds[3] - bounds[1],
                    colorRank: colorRank // 1: Đỏ, 2: Tím, 3: Khác
                });
            }
        }

        // Khôi phục lại trạng thái hiển thị ban đầu
        for (var r = 0; r < selectedIDs.length; r++) {
            setLayerVisibilityByID(selectedIDs[r], originalVisibilities[selectedIDs[r]]);
        }

        if (layersInfo.length === 0) {
            alert("Không thể đọc thông tin các layer được chọn!");
            app.preferences.rulerUnits = originalRulerUnits;
        } else {
            // 4. SẮP XẾP ƯU TIÊN: ĐỎ (1) -> TÍM (2) -> KHÁC (3) -> VỊ TRÍ GỐC TỪ TRÊN XUỐNG
            layersInfo.sort(function (a, b) {
                if (a.colorRank !== b.colorRank) {
                    return a.colorRank - b.colorRank;
                }
                return a.top - b.top;
            });

            // 5. TÍNH VỊ TRÍ GỐC (TOP-LEFT) CỦA NHÓM LAYER ĐƯỢC CHỌN
            var itemWidth = layersInfo[0].width;
            var itemHeight = layersInfo[0].height;

            var minX = layersInfo[0].left;
            var minY = layersInfo[0].top;

            for (var m = 1; m < layersInfo.length; m++) {
                if (layersInfo[m].left < minX) minX = layersInfo[m].left;
                if (layersInfo[m].top < minY) minY = layersInfo[m].top;
            }

            // 6. DỊCH CHUYỂN TẤT CẢ LAYER VÀO ĐÚNG 1 CỘT DUY NHẤT
            var redCount = 0;
            var purpleCount = 0;
            var otherCount = 0;

            for (var k = 0; k < layersInfo.length; k++) {
                var item = layersInfo[k];

                if (item.colorRank === 1) redCount++;
                else if (item.colorRank === 2) purpleCount++;
                else otherCount++;

                var targetX = minX;
                var targetY = minY + (k * itemHeight);

                var dx = targetX - item.left;
                var dy = targetY - item.top;

                translateLayerByID(item.id, dx, dy);
            }

            // 7. BÔI CHỌN LẠI TOÀN BỘ CÁC LAYER ĐÃ SẮP XẾP
            selectMultipleLayersByIDs(selectedIDs);

            app.preferences.rulerUnits = originalRulerUnits;

            alert("🎉 ĐÃ GHÉP " + layersInfo.length + " XE THÀNH 1 CỘT THEO MÀU THÀNH CÔNG!\n" +
                  "-----------------------------------------\n" +
                  "🔴 Nền Đỏ (Ưu tiên 1) : " + redCount + " xe\n" +
                  "🟣 Nền Tím (Ưu tiên 2) : " + purpleCount + " xe\n" +
                  "⚪ Nền Khác (Ưu tiên 3): " + otherCount + " xe\n" +
                  "-----------------------------------------\n" +
                  "Thứ tự sắp xếp: Đỏ ➔ Tím ➔ Khác");
        }
    }
}

// ==============================================================================
// HÀM NHẬN DIỆN MÀU NỀN CỦA THẺ XE (RGB -> HSV SAMPLING)
// ==============================================================================
function detectLayerColorType(bounds, doc) {
    var left = bounds[0];
    var top = bounds[1];
    var right = bounds[2];
    var bottom = bounds[3];
    var width = right - left;
    var height = bottom - top;

    // Chọn các điểm lấy mẫu nền xung quanh xe (tránh xe ở giữa và icon góc)
    var samplePoints = [
        [left + width * 0.08, top + height * 0.50], // Biên giữa bên trái
        [left + width * 0.92, top + height * 0.50], // Biên giữa bên phải
        [left + width * 0.20, top + height * 0.88], // Đáy dưới bên trái
        [left + width * 0.80, top + height * 0.88], // Đáy dưới bên phải
        [left + width * 0.50, top + height * 0.12], // Đỉnh trên ở giữa
        [left + width * 0.50, top + height * 0.92]  // Đáy dưới ở giữa
    ];

    var redVotes = 0;
    var purpleVotes = 0;
    var otherVotes = 0;

    for (var i = 0; i < samplePoints.length; i++) {
        var sx = Math.round(samplePoints[i][0]);
        var sy = Math.round(samplePoints[i][1]);

        // Giới hạn trong kích thước canvas
        if (sx < 0) sx = 0;
        if (sx >= doc.width.as("px")) sx = doc.width.as("px") - 1;
        if (sy < 0) sy = 0;
        if (sy >= doc.height.as("px")) sy = doc.height.as("px") - 1;

        try {
            var sampler = doc.colorSamplers.add([UnitValue(sx, "px"), UnitValue(sy, "px")]);
            var rgb = sampler.color.rgb;
            var r = rgb.red;
            var g = rgb.green;
            var b = rgb.blue;
            sampler.remove();

            // Bỏ qua màu trắng (chữ/logo) hoặc màu quá tối
            if (r > 240 && g > 240 && b > 240) continue;
            if (r < 15 && g < 15 && b < 15) continue;

            var hsv = rgbToHsv(r, g, b);

            // Bỏ qua icon tích cam ở góc trên trái (Hue 20..48, S > 60)
            if (hsv.h >= 20 && hsv.h <= 48 && hsv.s > 60) continue;

            // 1. NỀN ĐỎ (Mythic): Hue 345..360 hoặc 0..18, Độ bão hòa S >= 25
            if ((hsv.h <= 18 || hsv.h >= 345) && hsv.s >= 25 && hsv.v >= 20) {
                redVotes++;
            }
            // 2. NỀN TÍM (Upgrade): Hue 265..345, Độ bão hòa S >= 25
            else if (hsv.h >= 265 && hsv.h < 345 && hsv.s >= 25 && hsv.v >= 20) {
                purpleVotes++;
            }
            // 3. NỀN KHÁC (Spy x Family / Xám / Tối / Xanh /...)
            else {
                otherVotes++;
            }
        } catch (e) {
            try { doc.colorSamplers.removeAll(); } catch (e2) { }
        }
    }

    try { doc.colorSamplers.removeAll(); } catch (e3) { }

    // Phân hạng màu theo số điểm bỏ phiếu
    if (redVotes >= 2 && redVotes >= purpleVotes) {
        return 1; // ĐỎ
    } else if (purpleVotes >= 2) {
        return 2; // TÍM
    } else if (redVotes > 0 && redVotes > purpleVotes) {
        return 1; // ĐỎ
    } else if (purpleVotes > 0) {
        return 2; // TÍM
    }
    return 3; // KHÁC / XÁM
}

// ==============================================================================
// HÀM CHUYỂN ĐỔI RGB SANG HSV
// ==============================================================================
function rgbToHsv(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    var max = Math.max(r, g, b), min = Math.min(r, g, b);
    var h, s, v = max;
    var d = max - min;
    s = max === 0 ? 0 : d / max;

    if (max === min) {
        h = 0;
    } else {
        switch (max) {
            case r: h = (g - b) / d + (g < b ? 6 : 0); break;
            case g: h = (b - r) / d + 2; break;
            case b: h = (r - g) / d + 4; break;
        }
        h /= 6;
    }

    return {
        h: h * 360, // 0..360 độ
        s: s * 100, // 0..100 %
        v: v * 100  // 0..100 %
    };
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
// HÀM ACTION MANAGER: LẤY VÀ ĐẶT TRẠNG THÁI HIỂN THỊ CỦA LAYER
// ==============================================================================
function getLayerVisibilityByID(layerID) {
    try {
        var ref = new ActionReference();
        ref.putIdentifier(charIDToTypeID("Lyr "), layerID);
        var desc = executeActionGet(ref);
        return desc.getBoolean(charIDToTypeID("Vsbl"));
    } catch (e) {
        return true;
    }
}

function setLayerVisibilityByID(layerID, visible) {
    try {
        var ref = new ActionReference();
        ref.putIdentifier(charIDToTypeID("Lyr "), layerID);
        var desc = new ActionDescriptor();
        desc.putReference(charIDToTypeID("null"), ref);
        executeAction(charIDToTypeID(visible ? "Shw " : "Hd  "), desc, DialogModes.NO);
    } catch (e) { }
}

// ==============================================================================
// HÀM ACTION MANAGER: DỊCH CHUYỂN LAYER THEO ID
// ==============================================================================
function translateLayerByID(layerID, dx, dy) {
    if (dx === 0 && dy === 0) return;

    try {
        var ref = new ActionReference();
        ref.putIdentifier(charIDToTypeID("Lyr "), layerID);
        var desc = new ActionDescriptor();
        desc.putReference(charIDToTypeID("null"), ref);
        executeAction(charIDToTypeID("slct"), desc, DialogModes.NO);

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
