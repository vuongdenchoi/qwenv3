"""
Color Analyzer - Calculates WCAG contrast ratio for bounding boxes using K-Means Clustering on the image crop.
"""
import numpy as np
from PIL import Image
from sklearn.cluster import KMeans
from io import BytesIO

def get_luminance(rgb):
    """
    Calculate the relative luminance of an RGB color (0-255)
    Formula: https://www.w3.org/TR/WCAG20/#relativeluminancedef
    """
    # Normalize RGB values
    r, g, b = [v / 255.0 for v in rgb]
    
    # Calculate relative luminance for each channel
    def channel_luminance(c):
        if c <= 0.03928:
            return c / 12.92
        else:
            return ((c + 0.055) / 1.055) ** 2.4
            
    R = channel_luminance(r)
    G = channel_luminance(g)
    B = channel_luminance(b)
    
    return 0.2126 * R + 0.7152 * G + 0.0722 * B

def get_contrast_ratio(l1, l2):
    """
    Calculate contrast ratio between two relative luminances.
    Formula: (L1 + 0.05) / (L2 + 0.05) where L1 is the lighter color.
    """
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)

def analyze_box_contrast(image_bytes: bytes, box: list) -> dict:
    """
    Cuts the image at the given bounding box [x1, y1, x2, y2],
    runs K-Means (K=2) to find foreground and background colors,
    and calculates the WCAG contrast ratio.
    """
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        x1, y1, x2, y2 = box
        cropped_img = img.crop((x1, y1, x2, y2))
        
        # Convert image to numpy array and reshape to a list of pixels
        pixels = np.array(cropped_img).reshape(-1, 3)
        
        # If the box is too small or flat, return None
        if len(pixels) < 2:
            return {"ratio": None, "pass": True, "error": "Box too small"}
            
        # KMeans clustering to find 2 dominant colors
        kmeans = KMeans(n_clusters=2, n_init=3, random_state=42)
        kmeans.fit(pixels)
        
        colors = kmeans.cluster_centers_
        
        # Calculate luminance for both colors
        lum1 = get_luminance(colors[0])
        lum2 = get_luminance(colors[1])
        
        ratio = get_contrast_ratio(lum1, lum2)
        
        # WCAG AA standard for normal text is 4.5
        passed = ratio >= 4.5
        
        return {
            "ratio": round(ratio, 2),
            "pass": passed,
            "colors": [colors[0].tolist(), colors[1].tolist()]
        }
    except Exception as e:
        return {"ratio": None, "pass": True, "error": str(e)}
