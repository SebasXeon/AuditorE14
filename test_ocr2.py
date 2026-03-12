import os
import numpy as np
from PIL import Image
from doctr.io import DocumentFile
from doctr.models import ocr_predictor
import time

from utils.image.crop import crop_by_division

model = ocr_predictor(det_arch='fast_tiny', reco_arch='crnn_mobilenet_v3_small', pretrained=True)


current_dir = os.path.dirname(os.path.abspath(__file__))
image_path = os.path.join(current_dir, "tests", "found", "candidate_4.png")
image_path2 = os.path.join(current_dir, "cropped.png")
im = Image.open(image_path)

cropped = im.crop((10,50, 80,150)) # crop_by_division(im, parts=8, start_part=1, stop_part=1)
cropped.save(image_path2)
#np_image = np.array(cropped)

doc = DocumentFile.from_images(image_path)
# Analyze
start_time = time.time()
result = model(doc)
end_time = time.time()
print(result)
print(f"OCR took {end_time - start_time:.2f} seconds")

json_export = result.export()
print(json_export)