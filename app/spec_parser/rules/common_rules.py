"""Shared rule constants."""

SYMPY_TYPE_TO_HANDLER = {
    "Piecewise": "_print_Piecewise",
    "Ne": "_print_Relational",
    "Eq": "_print_Relational",
    "Relational": "_print_Relational",
    "sinc": "_print_sinc",
    "ccode": "ccode",
}

PRINTING_TARGET_FILES = [
    "sympy/printing/ccode.py",
    "sympy/printing/codeprinter.py",
]

MATRIX_TARGET_FILES = [
    "sympy/matrices/matrices.py",
]
