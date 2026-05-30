"""WordPaper MVP API for academic `.docx` inspection, patching, and validation."""

from .ir import export_ir
from .patch import apply_patch
from .validator import validate_docx
from .academic import (
    analyze_writing,
    audit_references,
    check_journal,
    extract_abstract,
    list_references,
    make_section_patch,
    plan_revision,
    review_manuscript,
)
from .compiler import compile_document
from .quality import evaluate_quality_gate

__all__ = [
    "analyze_writing",
    "apply_patch",
    "audit_references",
    "check_journal",
    "compile_document",
    "export_ir",
    "evaluate_quality_gate",
    "extract_abstract",
    "list_references",
    "make_section_patch",
    "plan_revision",
    "review_manuscript",
    "validate_docx",
]
