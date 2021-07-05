"""
Data representation classes for interactive components.
"""

import time
from uuid import uuid4

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from alfred3.util import prefix_keys_safely
from pymongo.collection import ReturnDocument

from ._util import saving_method












