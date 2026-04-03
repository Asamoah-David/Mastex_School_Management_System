import re

with open("schoolms/operations/views.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find id_card_pdf and staff_id_card_pdf function definitions
matches = re.findall(r'def (id_card_pdf|staff_id_card_pdf).*?(?=\ndef |\Z)', content, re.DOTALL)

for match in matches[:2]:  # First two matches
    print("=" * 50)
    print(match[:500])  # First 500 chars of each function