"""Build and run a named Term product, then compare with the built-in product."""

import sys

from worked import inputs, project, same_outputs, setup, verify

folder = setup(sys.argv[1])
cfg = inputs(folder)
actual = project(folder, cfg, "TUTORIAL_TERM", "my-term")
expected = project(folder, cfg, "TERM", "builtin-term")
same_outputs(actual, expected)
verify(actual)
print("PASS: own Term factory matches every built-in aggregate column")
