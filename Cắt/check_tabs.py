import os
import cv2
import numpy as np

def read_img(path):
    data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)

src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "input")
files = sorted([f for f in os.listdir(src_dir) if f.lower().endswith(('.png', '.jpg'))])

for f in files:
    img = read_img(os.path.join(src_dir, f))
    H, W = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # Blue mask
    blue_mask = cv2.inRange(hsv, np.array([100, 150, 150]), np.array([130, 255, 255]))
    
    st_blue = np.where(blue_mask[:, int(2420*W/2778):int(2445*W/2778)] > 0)[0]
    mt_blue = np.where(blue_mask[:, int(2550*W/2778):int(2575*W/2778)] > 0)[0]
    
    st_y = float(np.median(st_blue)) if len(st_blue) > 20 else -1.0
    mt_y = float(np.median(mt_blue)) if len(mt_blue) > 20 else -1.0
    
    print(f"{f}: maintab_y={mt_y:5.0f} | subtab_y={st_y:5.0f}")
