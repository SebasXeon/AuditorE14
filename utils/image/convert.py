from PIL import Image
import cv2
import numpy as np

# Convert PIL to numpy array
def pil_to_np(image: Image.Image) -> np.ndarray:
    return np.array(image)

# Convert numpy array to PIL
def np_to_pil(array: np.ndarray) -> Image.Image:
    return Image.fromarray(array)

# Convert PIL to OpenCV format (BGR)
def pil_to_cv2(image: Image.Image) -> np.ndarray:
    rgb = np.array(image.convert("RGB"))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    return bgr

# Convert OpenCV format (BGR) to PIL
def cv2_to_pil(image: np.ndarray) -> Image.Image:
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)