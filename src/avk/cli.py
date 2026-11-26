"""Command-line entry point; only this boundary maps errors to process exit codes."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from avk.api import check, compile, run, version
from avk.demo.generate import add_generate_arguments, generate
from avk.runs.scenarios import generate_scenarios, scenario_library
from avk.runtime.errors import AvkError


def main(argv: Sequence[str] | None = None) -> int:
    """Return 0 on success, 1 for AvkError; argparse exits 2 for usage errors."""
    try:
        parser = argparse.ArgumentParser(prog="avk", description="Actuarial projection models")
        parser.add_argument("--version", action="version", version=version())
        commands = parser.add_subparsers(dest="command")
        runner = commands.add_parser("run", help="Validate, project and write one run")
        runner.add_argument("config")
        runner.add_argument("--root")
        runner.add_argument("--output", help="output folder (replaces the run's Output_path)")
        runner.add_argument(
            "--diagnostics", help="folder for every column of every policy-month (small books)"
        )
        checker = commands.add_parser("check", help="Validate the run and its input tables")
        checker.add_argument("config")
        checker.add_argument("--root")
        checker.add_argument("--dump-inputs")
        compiler = commands.add_parser(
            "compile",
            help="Build product kernels into the cache (every product if none named)",
        )
        compiler.add_argument(
            "codes", nargs="*", metavar="CODE", help="a product code or a product source file"
        )
        compiler.add_argument(
            "--device", default="cpu", help="execution device (cpu only in this release)"
        )
        depth = compiler.add_mutually_exclusive_group()
        depth.add_argument(
            "--explain", action="store_true", help="print passes, columns and manifests"
        )
        depth.add_argument(
            "--list",
            action="store_true",
            help="print code, composition, bases and identity (compiles nothing)",
        )
        demo = commands.add_parser("demo", help="Work with invented demonstration books")
        demo_actions = demo.add_subparsers(dest="action", required=True)
        add_generate_arguments(demo_actions.add_parser("generate", help="Generate a demo book"))
        scenarios = commands.add_parser("scenarios", help="Write supplied scenario files")
        scenario_actions = scenarios.add_subparsers(dest="action", required=True)
        scenario_generate = scenario_actions.add_parser(
            "generate", help="Run the scenario generator"
        )
        scenario_generate.add_argument("run_file", type=Path)
        scenario_generate.add_argument("output", type=Path)
        library = scenario_actions.add_parser(
            "library", help="Apply deterministic scenario overlays"
        )
        library.add_argument("run_file", type=Path)
        library.add_argument("library_file", type=Path)
        library.add_argument("folder", type=Path)
        args = parser.parse_args(argv)
        if args.command == "demo":
            print(generate(args.folder, args.product, args.count, args.seed))
        elif args.command == "scenarios":
            if args.action == "generate":
                print(generate_scenarios(args.run_file, args.output))
            else:
                for path in scenario_library(args.run_file, args.library_file, args.folder):
                    print(path)
        elif args.command == "run":
            result = run(
                args.config, root=args.root, diagnostics=args.diagnostics, output=args.output
            )
            seconds = result.timings.get("compile", 0.0)
            kernels = ", ".join(
                f"{code} {identity[:16]}; "
                + (
                    f"cache hit, loaded in {seconds:.2f} s"
                    if result.cache_hits.get(code)
                    else f"compiled in {seconds:.2f} s"
                )
                for code, identity in result.kernels.items()
            )
            print(
                f"{result.run_type} complete: {len(result.files)} files written (kernel {kernels})"
            )
            for note in result.notes:
                print(f"  {note}")
            for path in result.files:
                print(f"  {path}")
        elif args.command == "check":
            report = check(args.config, root=args.root, dump_inputs=args.dump_inputs)
            print("Input check passed")
            for text in report.product_summaries:
                print(f"  {text}")
        elif args.command == "compile":
            infos = compile(args.codes, device=args.device, explain=args.explain, listing=args.list)
            for number, info in enumerate(infos):
                if info.explanation is not None:
                    print(("\n" if number else "") + info.explanation, end="")
                elif args.list:
                    name, *bases = info.composition
                    print(
                        f"{info.code}  {name}={'+'.join(bases)}  {','.join(info.bases)}  "
                        f"{info.identity}"
                    )
                else:
                    columns = f"{len(info.columns)} column{'s' if len(info.columns) != 1 else ''}"
                    passes = f"{len(info.passes)} pass{'es' if len(info.passes) != 1 else ''}"
                    seconds = info.compile_seconds or 0.0
                    built = (
                        f"cache hit, loaded in {seconds:.2f} s"
                        if info.cache_hit
                        else f"compiled in {seconds:.2f} s"
                    )
                    identity = (info.identity or "")[:16]
                    print(
                        f"{info.code}: {columns} in {passes} on bases {', '.join(info.bases)}; "
                        f"identity {identity}; {built}"
                    )
        else:
            parser.print_help()
        return 0
    except AvkError as error:
        print(f"avk: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
