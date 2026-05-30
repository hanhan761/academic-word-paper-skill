"""WordPaper MVP API for academic `.docx` inspection, patching, and validation."""

from .ir import export_ir
from .patch import apply_patch
from .validator import validate_docx
from .academic import (
    analyze_writing,
    check_journal,
    extract_abstract,
    list_references,
    make_section_patch,
    plan_revision,
    review_manuscript,
)

__all__ = [
    "analyze_writing",
    "apply_patch",
    "check_journal",
    "export_ir",
    "extract_abstract",
    "list_references",
    "make_section_patch",
    "plan_revision",
    "review_manuscript",
    "validate_docx",
]
