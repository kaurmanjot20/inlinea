
import fitz
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
            
