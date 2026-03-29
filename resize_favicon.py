"""Resize favicon to all required sizes"""
from PIL import Image

source = r"c:\Users\Bernard\Desktop\Mastex_School_Management_System\schoolms\static\favicon.png"
output_dir = r"c:\Users\Bernard\Desktop\Mastex_School_Management_System\schoolms\static"

sizes = [512, 192, 180, 64, 32]
img = Image.open(source)

for size in sizes:
    resized = img.resize((size, size), Image.Resampling.LANCZOS)
    resized.save(f"{output_dir}/favicon_{size}.png", "PNG")
    print(f"Created favicon_{size}.png")

print("Done!")