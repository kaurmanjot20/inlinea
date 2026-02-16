#!/usr/bin/env python3
"""Quick verification script for the embedded annotations migration."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

results = []

# 1. Test PyMuPDF import
try:
    import fitz
    results.append(f"[OK] PyMuPDF imported: {fitz.VersionBind}")
except ImportError as e:
    results.append(f"[FAIL] PyMuPDF import: {e}")

# 2. Test store module
try:
    from pdf_app.document.store import Annotation, AnnotationStore
    store = AnnotationStore()
    ann = Annotation.create(type='highlight', page_index=0, rects=[(10,20,100,15)])
    assert ann.is_own == True
    store.add(ann)
    assert store.is_dirty == True
    assert len(store.annotations) == 1
    
    # Test undo
    store.undo()
    assert len(store.annotations) == 0
    
    # Test redo
    store.redo()
    assert len(store.annotations) == 1
    
    results.append("[OK] store.py: Annotation, AnnotationStore, undo/redo")
except Exception as e:
    results.append(f"[FAIL] store.py: {e}")

# 3. Test pdf_storage module imports
try:
    from pdf_app.document.pdf_storage import load_annotations_from_pdf, save_annotations_to_pdf
    results.append("[OK] pdf_storage.py: imports clean")
except Exception as e:
    results.append(f"[FAIL] pdf_storage.py: {e}")

# 4. Test load from a non-existent file (should return empty list, not crash)
try:
    anns = load_annotations_from_pdf("/tmp/nonexistent.pdf")
    assert anns == []
    results.append("[OK] pdf_storage.py: graceful handling of missing file")
except Exception as e:
    results.append(f"[FAIL] pdf_storage.py missing file: {e}")

# 5. Verify JSON sidecar code is removed
try:
    store2 = AnnotationStore()
    assert not hasattr(store2, 'save'), "save() should be removed"
    assert not hasattr(store2, 'load'), "load() should be removed"
    assert not hasattr(store2, 'save_to_file'), "save_to_file() should be removed"
    assert not hasattr(store2, 'load_from_file'), "load_from_file() should be removed"
    assert not hasattr(store2, 'get_fingerprint'), "get_fingerprint() should be removed"
    results.append("[OK] store.py: JSON sidecar methods removed")
except AssertionError as e:
    results.append(f"[FAIL] store.py dead code: {e}")

# Print results
for r in results:
    print(r)

if any("[FAIL]" in r for r in results):
    sys.exit(1)
else:
    print("\nAll checks passed!")
    sys.exit(0)
