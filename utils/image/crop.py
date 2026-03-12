from PIL import Image

def crop_by_division(img: Image.Image, parts: int, start_part: int, stop_part: int | None = None) -> Image.Image:
    """
    Crop a PIL image by dividing it vertically into equal parts.

    Args:
        img: PIL Image.
        parts: Number of divisions of the image.
        start_part: 1-based index of the starting part.
        stop_part: Optional 1-based index of the ending part (inclusive).
                   If None, crop until the last part.

    Returns:
        Cropped PIL Image.
    """

    if parts <= 0:
        raise ValueError("parts must be > 0")

    if start_part < 1 or start_part > parts:
        raise ValueError("start_part must be between 1 and parts")

    if stop_part is None:
        stop_part = parts

    if stop_part < start_part or stop_part > parts:
        raise ValueError("stop_part must be between start_part and parts")

    width, height = img.size
    part_width = width / parts

    left = int((start_part - 1) * part_width)
    right = int(stop_part * part_width)

    return img.crop((left, 0, right, height))