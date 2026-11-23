"""Public output labels and their product-column bindings."""

from avk.products.term.output_columns import BE_LAYER as TERM_BE
from avk.products.term.output_columns import PRESENT_VALUES as PRESENT_VALUES

BE_LAYER = tuple(
    (name, col)
    for name, col in TERM_BE
    if name not in ("be_death_benefits", "part1_sm", "part2_sm")
) + (("be_adb_benefit", "adb_benefit"),)

CI_BE_LAYER = tuple((name, col) for name, col in BE_LAYER if name != "be_adb_benefit") + (
    ("be_ci_benefit", "event_benefit"),
    ("be_wop_benefit", "wop_benefit"),
)
