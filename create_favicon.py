"""
Create a professional favicon using the user's original image with proper positioning.
"""
from PIL import Image, ImageDraw
import os

def create_clean_favicon():
    # Source image path - use the original image
    source_path = r"C:\Users\Bernard\AppData\Local\Temp\temp_image_1774817473812.png"
    output_path = r"c:\Users\Bernard\Desktop\Mastex_School_Management_System\schoolms\static\favicon.png"
    
    # Check if source exists
    if not os.path.exists(source_path):
        print(f"Source image not found: {source_path}")
        return False
    
    try:
        # Open the source image - keep original colors
        img = Image.open(source_path).convert("RGBA")
        original_width, original_height = img.size
        print(f"Original image size: {original_width}x{original_height}")
        
        # Create sizes for different contexts
        sizes = {
            512: (512, 512),
            192: (192, 192),
            180: (180, 180),
            64: (64, 64),
            32: (32, 32)
        }
        
        # Process each size
        for size_name, (size, _) in sizes.items():
            # Create a new image with dark background matching project
            new_img = Image.new("RGBA", (size, size), (15, 23, 42, 255))  # #0f172a
            
            # Calculate proper centering with good padding (10% of size)
            padding = int(size * 0.10)
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
            
            # Ensure minimum size
            new_width = max(new_width, int(size * 0.5))
            new_height = max(new_height, int(size * 0.5))
            
            # Resize with high quality LANCZOS
            img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Center the image
            paste_x = (size - new_width) // 2
            paste_y = (size - new_height) // 2
            
            # Paste onto background
            new_img.paste(img_resized, (paste_x, paste_y), img_resized)
            
            # Add subtle rounded corners
            from PIL import ImageDraw
            
            # Create rounded mask
            mask = Image.new("L", (size, size), 0)
            mask_draw = ImageDraw.Draw(mask)
            corner_radius = int(size * 0.15)  # 15% corner radius
            
            # Draw rounded rectangle on mask
            mask_draw.rounded_rectangle([(0, 0), (size-1, size-1)], corner_radius, fill=255)
            
            # Apply mask to image
            result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            result.paste(new_img, (0, 0))
            result.putalpha(mask)
            
            # Save
            if size_name == 512:
                result.save(output_path, "PNG")
                print(f"Saved: {output_path}")
            else:
                small_path = output_path.replace(".png", f"_{size_name}.png")
                result.save(small_path, "PNG")
                print(f"Saved: {small_path}")
        
        return True
        
    except Exception as e:
        print(f"Error creating favicon: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    create_clean_favicon()