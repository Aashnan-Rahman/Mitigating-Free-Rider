"""Paper-guided detector implementations used for overhead comparisons.

These modules are deliberately separate from the SWT-CP training path.  A
comparison run must never change or overwrite an existing experiment.
"""

from comparison.frad import FradDetector, FradInputs
from comparison.frida import FridaLossDetector

__all__ = ["FradDetector", "FradInputs", "FridaLossDetector"]
