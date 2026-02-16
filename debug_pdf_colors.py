
import fitz

# Load the PDF file from the user's directory.
# The user presumably just saved to a file, maybe the original one?
# I'll try to find a PDF in the directory or create a test one.
# But wait, I can just use the provided path if I knew it.
# The user ran `python3 main.py`, which likely opens a default PDF or asks for one.
# Let's assume there is a PDF file in the current directory or a known location.
# Based on previous logs, the user was working with `/mnt/A2463BFE463BD231/Users/kaurm/Code/test_folder/linux-pdf-editor/test.pdf`?
# I saw "Loaded PDF with 13 pages." in the user request.
# I'll search for PDFs in the current directory.

import glob
pdfs = glob.glob("*.pdf")
if not pdfs:
    print("No PDF found.")
    exit()

filename = pdfs[0] # Take the first one found
print(f"Checking {filename}...")

doc = fitz.open(filename)
for page in doc:
    for annot in page.annots():
        if annot.type[0] == fitz.PDF_ANNOT_SQUARE:
            print(f"Found Square Annotation on page {page.number}")
            print(f"  Colors: {annot.colors}")
            print(f"  Opacity: {annot.opacity}")
            print(f"  Border: {annot.border}")
            
