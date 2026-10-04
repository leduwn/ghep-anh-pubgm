import cv2
import os

video_path = r'd:\Ghep-Anh\1787137775972_7994954700336769707_7994954700336769707.mp4'
out_dir = r'd:\Ghep-Anh\docs'
os.makedirs(out_dir, exist_ok=True)

cap = cv2.VideoCapture(video_path)
fps = cap.get(cv2.CAP_PROP_FPS)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"FPS={fps}, Total={total}, W={w}, H={h}, Duration={total/fps:.1f}s")

# Extract 10 evenly spaced frames
step = max(1, total // 10)
for i, frame_idx in enumerate(range(0, total, step)):
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    if ret:
        out_path = os.path.join(out_dir, f'frame_{i:02d}.jpg')
        cv2.imwrite(out_path, frame)
        print(f"Saved frame {frame_idx} -> {out_path}")

cap.release()
print("Done")
