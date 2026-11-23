"""Reuse Term loading, policy preparation, validation and output contracts."""

from avk.outputs.schema import OutputSchema
from avk.products.term.factory import TermFactory
from tutorial_products.formulas import MyTerm, ReturnTerm


class MyTermFactory(TermFactory):
    code = "TUTORIAL_TERM"
    definition_class = MyTerm


class ReturnFactory(MyTermFactory):
    code = "TUTORIAL_ROP"
    definition_class = ReturnTerm

    def output_schema(self, run_type: str) -> OutputSchema:
        original = super().output_schema(run_type)
        return OutputSchema(
            entries=original.entries + (("returned_premiums_BE", "returned_premiums", "be"),),
            keys=original.keys,
            integer_keys=original.integer_keys,
            seriatim=original.seriatim,
        )
