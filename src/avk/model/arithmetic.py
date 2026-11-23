"""Scalar arithmetic support shared by preparation and self-contained emitted modules.

CREDIT_LIFE's loan recursion uses an explicit fused multiply-add to round the
multiply/subtract once, including near-zero balances. Other arithmetic is uncontracted.
The registration source is included verbatim in generated kernel identities.
"""

import math

from llvmlite import ir as llvm_ir  # type: ignore[import-untyped]
from numba import types
from numba.extending import intrinsic, overload

FMA_SUPPORT = """
@intrinsic
def _fma_intrinsic(typingctx, a, b, c):
    signature = types.float64(types.float64, types.float64, types.float64)
    def codegen(context, builder, signature, args):
        dtype = args[0].type
        function = builder.module.declare_intrinsic("llvm.fma", [dtype],
            llvm_ir.FunctionType(dtype, [dtype, dtype, dtype]))
        return builder.call(function, args)
    return signature, codegen


@overload(math.fma)
def _overload_fma(a, b, c):
    def impl(a, b, c):
        return _fma_intrinsic(a, b, c)
    return impl
"""

# Registration is compile-time only; numeric paths use math.fma/LLVM directly.
exec(
    FMA_SUPPORT,
    {
        "math": math,
        "llvm_ir": llvm_ir,
        "types": types,
        "intrinsic": intrinsic,
        "overload": overload,
    },
)
