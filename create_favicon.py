"""
Create a professional favicon using the user's image with project colors.
"""
from PIL import Image, ImageFilter, ImageEnhance
import os

# Project colors
PRIMARY_GREEN = (34, 197, 94)  # #22c55e
DARK_GREEN = (22, 163, 74)      # #16a34a
DEEP_GREEN = (2, 44, 34)        # #022c22
BG_DARK = (15, 23, 42)          # #0f172a

def create_professional_favicon():
    # Source image path
    source_path = r"C:\Users\Bernard\AppData\Local\Temp\temp_image_1774817473812.png"
    output_path = r"c:\Users\Bernard\Desktop\Mastex_School_Management_System\schoolms\static\favicon.png"
    
    # Check if source exists
    if not os.path.exists(source_path):
        print(f"Source image not found: {source_path}")
        return False
    
    try:
        # Open the source image
        img = Image.open(source_path).convert("RGBA")
        original_width, original_height = img.size
        print(f"Original image size: {original_width}x{original_height}")
        
        # Create a new image with dark background
        size = 512
        new_img = Image.new("RGBA", (size, size), BG_DARK)
        
        # Calculate centering with padding (15% margin)
        padding = int(size * 0.15)
        content_size = size - (padding * 2)
        
        # Resize image maintaining aspect ratio to fit in content area
        img_ratio = original_width / original_height
        if img_ratio > 1:
            # Landscape
            new_width = content_size
            new_height = int(content_size / img_ratio)
        else:
            # Portrait or square
            new_height = content_size
            new_width = int(content_size * img_ratio)
        
        # Resize with high quality
        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Apply green color transformation
        # Convert to RGB, apply green tint, then back to RGBA
        img_rgb = img_resized.convert("RGB")
        
        # Apply color transformation: map dark colors to green, light to light green
        pixels = img_rgb.load()
        width, height = img_rgb.size
        
        for y in range(height):
            for x in range(width):
                r, g, b = pixels[x, y]
                
                # Calculate luminance
                lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
                
                if lum < 0.3:  # Dark areas -> Dark green
                    pixels[x, y] = (
                        int(PRIMARY_GREEN[0] * 0.3),
                        int(PRIMARY_GREEN[1] * 0.8),
                        int(PRIMARY_GREEN[2] * 0.5)
                    )
                elif lum < 0.6:  # Mid tones -> Primary green
                    pixels[x, y] = (
                        int(PRIMARY_GREEN[0] * 0.7),
                        int(PRIMARY_GREEN[1] * 0.95),
                        int(PRIMARY_GREEN[2] * 0.8)
                    )
                else:  # Light areas -> Light green
                    pixels[x, y] = (
                        int(min(255, PRIMARY_GREEN[0] + 50)),
                        int(min(255, PRIMARY_GREEN[1] + 30)),
                        int(min(255, PRIMARY_GREEN[2] + 20))
                    )
        
        # Add slight glow effect
        img_processed = img_rgb.filter(ImageFilter.GaussianBlur(radius=1))
        enhancer = ImageEnhance.Contrast(img_processed)
        img_processed = enhancer.enhance(1.2)
        
        # Convert back to RGBA
        img_final = img_processed.convert("RGBA")
        
        # Paste in center
        paste_x = (size - new_width) // 2
        paste_y = (size - new_height) // 2
        new_img.paste(img_final, (paste_x, paste_y), img_final)
        
        # Add rounded corners
        from PIL import ImageDraw
        
        # Create mask for rounded corners
        mask = Image.new("L", (size, size), 0)
        mask_draw = ImageDraw.Draw(mask)
        corner_radius = 80
        
        # Draw rounded rectangle
        mask_draw.rounded_rectangle([(0, 0), (size-1, size-1)], corner_radius, fill=255)
        
        # Apply mask
        result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        result.paste(new_img, (0, 0))
        
        # Apply corner mask
        temp = result.copy()
        result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        result.paste(temp, (0, 0), mask)
        
        # Add subtle border glow
        border = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        border_draw = ImageDraw.Draw(border)
        border_draw.rounded_rectangle(
            [(0, 0), (size-1, size-1)], 
            corner_radius, 
            outline=PRIMARY_GREEN, 
            width=3
        )
        border_blur = border.filter(ImageFilter.GaussianBlur(radius=5))
        
        # Combine
        final = Image.alpha_composite(result, border_blur)
        
        # Save
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        final.save(output_path, "PNG", optimize=True)
        print(f"Favicon saved to: {output_path}")
        
        # Also create smaller sizes
        sizes = [192, 180, 64, 32]
        for s in sizes:
            small = final.resize((s, s), Image.Resampling.LANCZOS)
            small_path = output_path.replace(".png", f"_{s}.png")
            small.save(small_path, "PNG", optimize=True)
            print(f"Created: {small_path}")
        
        return True
        
    except Exception as e:
        print(f"Error creating favicon: {e}")
        return False

if __name__ == "__main__":
    create_professional_favicon()