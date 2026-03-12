import os
import asyncio
from PIL import Image
import winrt.windows.storage.streams as streams
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat
import time

from utils.image.crop import crop_by_division

def pil_to_software_bitmap(path):
    img = Image.open(path).convert("RGBA")
    writer = streams.DataWriter()
    writer.write_bytes(img.tobytes())
    bitmap = SoftwareBitmap(BitmapPixelFormat.RGBA8, img.width, img.height)
    bitmap.copy_from_buffer(writer.detach_buffer())
    return bitmap

async def recognize_async(image_path):
    bitmap = pil_to_software_bitmap(image_path)
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise RuntimeError("No OCR engine for user languages available")
    result = await engine.recognize_async(bitmap)
    return result.text

current_dir = os.path.dirname(os.path.abspath(__file__))
image_path = os.path.join(current_dir, "tests", "found", "candidate_3.png")
image_path2 = os.path.join(current_dir, "cropped.png")
im = Image.open(image_path)

cropped = im.crop((10,50, 80,150)) # crop_by_division(im, parts=8, start_part=1, stop_part=1)
cropped.save(image_path2)


# Analyze
start_time = time.time()

text = asyncio.run(recognize_async(image_path2))


end_time = time.time()
print(text)
print(f"OCR took {end_time - start_time:.2f} seconds")