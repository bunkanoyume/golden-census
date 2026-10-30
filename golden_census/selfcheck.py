"""golden-census's own controls: every guard shipped with the planted case that
proves it can go red.

A zero result is not a clean result. Each control below plants one change and
asserts golden-census's verdict on it; an arm this machine cannot exercise is a
disclosed SKIP, never a pass. The whole self-check REFUSES (exit 2) on a
`Refusal`, reports a raise as `[FAIL] !` and exit 1, and prints the rows
collected before either — a self-check that aborts has reported nothing, and a
comparator that has reported nothing must not compare.

Every arm is named by a letter, and that letter is the row's name in the
output.
"""

from __future__ import annotations

import functools
import io
import json
import os
import re
from collections.abc import Callable
from typing import Any

from .capture import (
    contraband_control,
)
from .cli import main
from .compare import diff_captures
from .controls import (
    CheckRow,
    Controls,
    SkipRow,
    block,
    manifest_controls,
)
from .core import (
    ACTUAL,
    Refusal,
    Roots,
    UNREPORTABLE,
    with_next,
)
from .docs import (
    docs_controls,
)
from .manifest import Manifest
from .proof import (
    _STUB_CENSUS,
    _box,
    _one_line,
    _quietly,
    _scratch,
)
from .checks_base import (
    _control_roots,
)
from .checks_capture import (
    _allow_comment_control,
    _allow_control,
    _allow_file_control,
    _allow_not_text_control,
    _cleanup_control,
    _compare_leak_control,
    _workspace_removal_control,
    _disclosure_control,
    _environmental_skip_control,
    _skip_shape_control,
    _final_newline_control,
    _line_ending_control,
    _json_regex_control,
    _marker_control,
    _empty_value_control,
    _not_a_directory_control,
    _out_guard_control,
    _staged_capture_control,
    _name_ends_control,
    _path_start_control,
    _temp_root_control,
    _platform_readers_control,
    _platform_record_control,
    _shared_invocation_control,
    _twice_partial_control,
    _twice_scratch_control,
    _undecodable_control,
    _both_skipped_control,
    _kept_cache_control,
    _address_folder_control,
    _cache_home_control,
    _clone_git_exit_control,
    _written_clone_control,
    _git_metadata_control,
    _global_config_control,
    _repo_global_ignore_control,
    _exported_git_dir_control,
    _vary_told_control,
    _about_ran_control,
    _control_characters_control,
    _passed_through_control,
    _subject_ran_control,
    _mutants_undecodable_control,
    _written_not_text_control,
    _cleared_path_control,
    _tallies_failing_control,
    _unreadable_control,
)
from .checks_census import (
    _UNPROVEN_PIN,
    _absent_program_control,
    _control_next_control,
    _drift_verdict_control,
    _record_argv_control,
    _scope_control,
    _fold_overlap_control,
    _unresolved_key_control,
    _census_prefix_control,
    _root_swallow_control,
    _stand_in_fold_control,
    _star_scope_control,
    _unknown_key_control,
    _escaping_name_control,
    _file_above_file_control,
    _unwritable_file_control,
    _case_folded_control,
    _normalized_name_control,
    _empty_pin_control,
    _dash_address_control,
    _password_address_control,
    _environment_control,
    _git_answer_control,
    _git_exit_control,
    _here_command_control,
    _here_control,
    _include_loader_control,
    _json_shapes_control,
    _loader_control,
    _loader_placeholder_control,
    _mutants_placeholder_control,
    _place_order_control,
    _python_fold_control,
    _regex_verdict_control,
    _reserved_writes_control,
    _short_name_fold_control,
    _spelled_root_fold_control,
    _state_expand_control,
    _set_as_surface_control,
    _surface_set_control,
    _matrix_args_control,
    _repeated_pin_control,
    _fixed_widths_control,
    _fixed_control_control,
    _alike_inputs_control,
    _two_counters_control,
    _own_pattern_control,
    _unopenable_control,
    _vary_place_control,
    _vary_red_control,
    _vary_refused_place_control,
    _vary_runs_control,
    _writes_in_env_control,
)
from .checks_documents import (
    _checkout_missing_document_control,
    _layout_from_package_control,
    _packaging_control,
    _read_only_fixture_control,
    _reference_capture_control,
    _shipped_layout_control,
    _unreadable_fixture_control,
)
from .checks_launch import (
    _against_line_control,
    _allow_early_control,
    _bad_byte_control,
    _closed_stdin_control,
    _closed_stdout_control,
    _command_override_control,
    _decoding_control,
    _dropped_flag_control,
    _dropped_next_control,
    _docs_exit_control,
    _early_paths_control,
    _floor_guard_control,
    _startup_noise_control,
    _given_again_control,
    _help_line_control,
    _launcher_control,
    _launcher_refusals_control,
    _module_as_script_control,
    _new_rows_next_control,
    _pending_control,
    _precedes_control,
    _private_root_control,
    _red_census_control_control,
    _report_parity_control,
    _stdout_encoding_control,
    _tally_control,
    _unanswered_error_control,
    _unusable_midway_control,
    _which_copy_control,
)
from .checks_mutants import (
    _clone_executes_control,
    _dirty_tree_control,
    _unclean_commit_control,
    _mutants_controls,
    _only_names_control,
    _refused_first_control,
    _other_kind_control,
    _escaping_mutant_control,
    _left_behind_control,
    _permitted_movement_control,
    _refused_capture_control,
    _streams_control,
    _with_root_control,
)
from .checks_probe import (
    _probe_controls,
)
from .checks_process import (
    _anchor_isolated_control,
    _group_line_control,
    _marker_env_control,
    _stop_control,
    _sweep_control,
)
from .checks_source import (
    _next_coverage_control,
    _no_clock_control,
    _no_cycle_control,
    _one_decider_control,
    _walk_fault_control,
    _width_owner_control,
)
from .checks_templates import (
    _hole_refusal_control,
    _init_checks_templates_control,
    _init_control,
    _init_leaves_nothing_control,
    _init_stays_inside_control,
    _source_outside_control,
    _neutral_template_control,
    _round_trip_control,
    _shipped_templates_control,
    _template_checker_control,
    _template_parity_control,
    _templates_present_control,
)
from .checks_width import (
    _cache_dotdot_control,
    _second_root_owned_control,
    _selftest_wide_root_control,
    _tmpdir_window_control,
    _two_root_control,
    _two_root_skip_control,
    _unusable_root_control,
    _wide_pin_control,
    _width_arithmetic_control,
)


# A small JSON document and a text line of golden-census's own. Nothing here
# names a subject: the controls state what the COMPARATOR does, and a
# comparator that only worked on one program's output would be no floor.
_CONTROL_DOCUMENT: dict[str, Any] = {
    "nodes": ["a", "b"],
    "edges": [{"from": "a", "to": "b", "count": 1}],
}

_CONTROL_LINE = "a -> b   (2 references)\n"

_CONTROL_REFUSAL = ("golden-census-control: error: --one and --two compose with "
                    "nothing; drop --two\n")


def _json_text(document: Any) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------- the controls


def _comparator_controls(check: CheckRow, roots: Roots) -> None:
    """(a, b, d, f) the four the comparator and the scan carry themselves: a
    planted edge in a copied JSON document, a planted byte in a recorded text
    line, a planted difference in a refusal's stderr, and the contraband
    scan's own positive control.

    A function like every other entry of the list, and for the same reason:
    four arms written inline in the runner are four the runner cannot guard
    one at a time, and their letters have nowhere to be read from.
    """
    # (a) a planted extra edge in a copied JSON document is reported.
    base = _json_text(_CONTROL_DOCUMENT)
    doctored = json.loads(base)
    doctored["edges"].append({"from": "b", "to": "a", "count": 1})
    a_diffs = diff_captures({"t/doc.json": base},
                            {"t/doc.json": _json_text(doctored)})
    check("a  a planted extra edge in a copied JSON document is REPORTED",
          len(a_diffs) == 1 and a_diffs[0].kind == "changed"
          and '"from": "b"' in a_diffs[0].detail,
          f"{ACTUAL}{[(d.path, d.kind) for d in a_diffs]}")

    # (b) a planted one-byte change in a text line is reported.
    b_diffs = diff_captures(
        {"t/report.out": _CONTROL_LINE},
        {"t/report.out": _CONTROL_LINE.replace("(2 references)",
                                               "(3 references)")})
    check("b  a planted one-byte change in a recorded text line is REPORTED",
          len(b_diffs) == 1 and b_diffs[0].kind == "changed"
          and "3 references" in b_diffs[0].detail,
          f"{ACTUAL}{[(d.path, d.kind) for d in b_diffs]}")

    # (d) a planted difference in a refusal's stderr is reported.
    d_diffs = diff_captures(
        {"_subject/matrix.err": _CONTROL_REFUSAL},
        {"_subject/matrix.err": _CONTROL_REFUSAL.replace("drop --two",
                                                         "drop --one")})
    check("d  a planted difference in a refusal's stderr is REPORTED",
          len(d_diffs) == 1 and d_diffs[0].kind == "changed"
          and "drop --one" in d_diffs[0].detail,
          f"{ACTUAL}{[(d.path, d.kind) for d in d_diffs]}")

    # (f) the contraband scan's own positive control.
    control_ok, control_detail = contraband_control(roots)
    check("f  the contraband scan fires on a planted home path",
          control_ok, f"{ACTUAL}{control_detail}")


def _without_skip(body: Callable[..., None], *rest: Any) -> Controls:
    """One entry of the guarded list, for a control that takes no `skip`.

    The list is walked with ONE call shape — `control(check, skip)` — because
    a guard written around each call cannot also be written per signature.
    The wrapped function's docstring travels with the adapter, so a row's
    letters are still read off the control and never off the wrapper.
    """
    @functools.wraps(body)
    def entry(check: CheckRow, _skip: SkipRow) -> None:
        body(check, *rest)
    return entry


#: The leading run of `(letters)` groups a control's docstring opens with:
#: `(yyyy) …` is one group and `(x) (y) (z) (aa) …` is four.
_DOC_LETTERS = re.compile(r"\s*\(([^)]*)\)")


def _letters_of(control: Controls) -> str:
    """The row letters a guarded control owns, read off its docstring.

    DERIVED, never typed a third time: the letters are already in the
    docstring and in the label the control prints, and a third copy here is
    the one that goes stale when an arm is renamed. A control whose docstring
    opens with no parenthesis is named by its own name instead, which is
    still enough for a reader to find it.
    """
    body = getattr(control, "func", control)
    doc = body.__doc__ or ""
    letters: list[str] = []
    position = 0
    while (found := _DOC_LETTERS.match(doc, position)) is not None:
        letters.append(found.group(1).strip())
        position = found.end()
    return ", ".join(letters) or getattr(body, "__name__", "a control")


def _run_controls(check: CheckRow, skip: SkipRow,
                  manifest: Manifest | None = None,
                  controls: list[Controls] | None = None,
                  out: Any = None) -> None:
    """Every self-test, in order, EACH ONE GUARDED.

    `check` records a PASS/FAIL row, `skip` a DISCLOSED SKIP — an arm this
    machine cannot exercise, which is never allowed to read as a pass.

    A self-test that raises or refuses is ONE self-test's fault, and the ones
    after it still run. Guarded as a block instead, a `Refusal` out of a
    single arm — a missing `git`, a fixture that could not be built — ends
    the run at its first problem and leaves every later self-test unreported,
    which is indistinguishable from arms nobody wrote. So the guard is HERE,
    once, around each call. `core.Report.guard` stays what it is, because
    `controls.block` is shared with the census controls that run in front of a
    reader's command, and there a refusal IS a statement about the run.

    `controls` is the list to walk and `None` means build the real one. It is
    built INSIDE this function because two entries need values only a call
    has — the control roots and the caller's manifest — and a default
    evaluated at `def` time can have neither. Control `nnnnn` hands its own
    list in.

    Every row the walk prints is counted by the name it opens with, and a
    name that opens two verdicts, or two SKIPs, is one red `!` row after the
    walk: arm `nnnnn` is its control. A SKIP beside a verdict of its own
    name is the half of one arm it could not exercise, and stands.

    `manifest_controls` is the one call that is NOT in the guarded list. Those
    rows are the reader's own census, reached by `--selfcheck --manifest M`,
    and a census control's `Refusal` must still end that run at exit 2 with
    `REFUSED after row N`, exactly as it does through `census_check`. `out`
    takes the line naming a work directory of the census's that stayed;
    `selfcheck` hands it a buffer and writes it after the block.
    """
    if controls is None:
        roots = _control_roots()
        controls = [
            _without_skip(_comparator_controls, roots),
            _without_skip(_out_guard_control),
            _without_skip(_staged_capture_control),
            _without_skip(_platform_record_control),
            _platform_readers_control,
            _without_skip(_name_ends_control),
            _without_skip(_path_start_control),
            _without_skip(_temp_root_control),
            _without_skip(_allow_control),
            _without_skip(_allow_file_control),
            _without_skip(_allow_not_text_control),
            _without_skip(_allow_comment_control),
            _without_skip(_unreadable_control, roots),
            _without_skip(_marker_control),
            _without_skip(_twice_scratch_control),
            _without_skip(_twice_partial_control),
            _without_skip(_final_newline_control),
            _without_skip(_line_ending_control),
            _without_skip(_control_characters_control),
            _without_skip(_json_regex_control),
            _without_skip(_not_a_directory_control),
            _without_skip(_empty_value_control),
            _without_skip(_undecodable_control),
            _without_skip(_both_skipped_control),
            _kept_cache_control,
            _address_folder_control,
            _cache_home_control,
            _clone_git_exit_control,
            _written_clone_control,
            _git_metadata_control,
            _global_config_control,
            _repo_global_ignore_control,
            _exported_git_dir_control,
            _vary_told_control,
            _about_ran_control,
            _without_skip(_passed_through_control),
            _subject_ran_control,
            _mutants_undecodable_control,
            _without_skip(_written_not_text_control),
            _without_skip(_cleared_path_control),
            _without_skip(_tallies_failing_control),
            functools.partial(_cleanup_control, manifest=manifest),
            _workspace_removal_control,
            _without_skip(_environment_control, manifest),
            _without_skip(_closed_stdout_control, manifest),
            _unusable_midway_control,
            _without_skip(_unanswered_error_control),
            _without_skip(_raise_control),
            _quiet_pass_control,
            _compare_leak_control,
            _without_skip(_disclosure_control),
            _without_skip(_skip_shape_control),
            _without_skip(_environmental_skip_control),
            _without_skip(_loader_control),
            _unopenable_control,
            _vary_red_control,
            _without_skip(_vary_runs_control),
            _vary_place_control,
            _vary_refused_place_control,
            _without_skip(_place_order_control),
            _without_skip(_drift_verdict_control),
            _without_skip(_regex_verdict_control),
            _without_skip(_json_shapes_control),
            _mutants_controls,
            _dirty_tree_control,
            _unclean_commit_control,
            _without_skip(_other_kind_control),
            _only_names_control,
            _refused_first_control,
            _escaping_mutant_control,
            _without_skip(_with_root_control),
            _clone_executes_control,
            _refused_capture_control,
            _permitted_movement_control,
            _left_behind_control,
            _streams_control,
            _without_skip(docs_controls),
            _one_decider_control,
            _no_cycle_control,
            _no_clock_control,
            _sweep_control,
            _group_line_control,
            _without_skip(_anchor_isolated_control),
            _stop_control,
            _marker_env_control,
            _width_owner_control,
            _without_skip(_loader_placeholder_control),
            _without_skip(_mutants_placeholder_control),
            _without_skip(_report_parity_control),
            _probe_controls,
            _next_coverage_control,
            _walk_fault_control,
            _floor_guard_control,
            _startup_noise_control,
            _launcher_control,
            _launcher_refusals_control,
            _without_skip(_module_as_script_control),
            _which_copy_control,
            _without_skip(_shipped_layout_control),
            _layout_from_package_control,
            _reference_capture_control,
            _without_skip(_checkout_missing_document_control),
            _unreadable_fixture_control,
            _read_only_fixture_control,
            _without_skip(_tmpdir_window_control),
            _width_arithmetic_control,
            _wide_pin_control,
            _without_skip(_docs_exit_control),
            _decoding_control,
            _stdout_encoding_control,
            _bad_byte_control,
            _closed_stdin_control,
            _pending_control,
            _templates_present_control,
            _source_outside_control,
            _init_checks_templates_control,
            _without_skip(_template_parity_control),
            _neutral_template_control,
            _init_control,
            _init_leaves_nothing_control,
            _init_stays_inside_control,
            _hole_refusal_control,
            _round_trip_control,
            _here_control,
            _without_skip(_here_command_control),
            _git_answer_control,
            _git_exit_control,
            _without_skip(_case_folded_control),
            _without_skip(_normalized_name_control),
            _without_skip(_reserved_writes_control),
            _without_skip(_empty_pin_control),
            _dash_address_control,
            _without_skip(_password_address_control),
            _without_skip(_absent_program_control),
            _without_skip(_state_expand_control),
            _without_skip(_include_loader_control),
            _two_root_control,
            _two_root_skip_control,
            _without_skip(_second_root_owned_control),
            _selftest_wide_root_control,
            _unusable_root_control,
            _cache_dotdot_control,
            _without_skip(_private_root_control),
            _without_skip(_tally_control),
            _shipped_templates_control,
            _template_checker_control,
            _without_skip(_writes_in_env_control),
            _without_skip(_python_fold_control),
            _without_skip(_spelled_root_fold_control),
            _short_name_fold_control,
            _without_skip(_surface_set_control),
            _without_skip(_set_as_surface_control),
            _without_skip(_matrix_args_control),
            _without_skip(_repeated_pin_control),
            _without_skip(_fixed_widths_control),
            _without_skip(_fixed_control_control),
            _without_skip(_alike_inputs_control),
            _without_skip(_two_counters_control),
            _without_skip(_own_pattern_control),
            _packaging_control,
            _without_skip(_shared_invocation_control),
            _control_next_control,
            _without_skip(_record_argv_control),
            _without_skip(_scope_control),
            _without_skip(_star_scope_control),
            _without_skip(_fold_overlap_control),
            _without_skip(_unresolved_key_control),
            _census_prefix_control,
            _root_swallow_control,
            _without_skip(_stand_in_fold_control),
            _without_skip(_unknown_key_control),
            _without_skip(_escaping_name_control),
            _without_skip(_file_above_file_control),
            _unwritable_file_control,
            _precedes_control,
            _dropped_flag_control,
            _given_again_control,
            _help_line_control,
            _allow_early_control,
            _command_override_control,
            _new_rows_next_control,
            _dropped_next_control,
            _against_line_control,
            _early_paths_control,
            _red_census_control_control,
            _without_skip(_guarded_walk_control),
        ]
    # Every row the walk prints, by the name it opens with — the letters a
    # reader quotes. Two verdicts of one name, or two SKIPs, are two claims
    # nobody can tell apart, and neither arm can see the other, so they are
    # counted here, where every row passes, and named in one red row after
    # the walk. A SKIP beside a verdict of its own name is one arm's half it
    # could not exercise, disclosed under the arm's name, and is not counted
    # against it.
    checked: list[str] = []
    skipped: list[str] = []

    def named_check(label: str, ok: bool, detail: str, *, next: str = "",
                    told: tuple[str, ...] = ()) -> None:
        checked.append(label.split(maxsplit=1)[0] if label.strip() else label)
        check(label, ok, detail, next=next, told=told)

    def named_skip(label: str, why: str) -> None:
        skipped.append(label.split(maxsplit=1)[0] if label.strip() else label)
        skip(label, why)

    for control in controls:
        try:
            control(named_check, named_skip)
        except Refusal as refused:
            check(f"!  {_letters_of(control)} REFUSED instead of reporting a "
                  "verdict — the self-tests after it still ran", False,
                  f"{ACTUAL}Refusal: "
                  f"{with_next(str(refused).split('. ')[0], refused)}")
        except Exception as exc:
            if isinstance(exc, UNREPORTABLE):
                raise
            check(f"!  {_letters_of(control)} raised instead of reporting a "
                  "verdict — the self-tests after it still ran", False,
                  f"{ACTUAL}{type(exc).__name__}: {exc}")
    twice = sorted({name for names in (checked, skipped) for name in names
                    if names.count(name) > 1})
    if twice:
        check(f"!  {', '.join(twice)} opens more than one row — a row's name "
              "is its own", False,
              ACTUAL + "; ".join(f"{name} opens {checked.count(name)} "
                                 f"verdict(s) and {skipped.count(name)} "
                                 "SKIP(s)" for name in twice),
              next="Give each row a name no other row of the self-check opens "
                   "with: the letters are what a reader quotes, and two rows "
                   "under one name are two claims nobody can tell apart.")
    if manifest is not None:
        manifest_controls(check, skip, manifest, out)


def _planted_entry(letters: str, body: Controls) -> Controls:
    """One entry of arm `nnnnn`'s planted list, with letters of its own.

    The letters go in a docstring and nowhere else, because that is where
    `_letters_of` reads a real control's from: an entry whose letters were
    handed to the walk another way would exercise a path no self-test takes.
    """
    body.__doc__ = f"({letters}) a planted entry of arm nnnnn's own list."
    return body


def _guarded_walk_control(check: CheckRow) -> None:
    """(nnnnn) a self-test that raises or refuses costs ONE row, and the
    self-tests after it still run.

    Three planted entries — one that passes, one that fails outright, one
    that passes — walked twice, with a `Refusal` in the middle and then with
    an `ImportError`. Both outer rows have to be there, the middle one has to
    be a single `[FAIL]  !` row naming the letters of the entry that broke,
    the exit code has to be 1 and not 2, and the tally must not say `REFUSED
    after row`: a refusal out of ONE self-test is not a statement about the
    run, and the row that says so is worth nothing if the rows after it are
    missing.

    A third list holds two entries whose rows open with one name, between
    two that do not, and one entry that prints a verdict and a SKIP under
    its own name: every row prints, and the walk ends in one `[FAIL]  !`
    row naming the two entries' name and not the third's, which is what
    keeps two arms from answering to one name in the real walk. A fourth
    holds two entries that each SKIP under one name, between two that pass:
    both SKIPs print and the walk ends in one `[FAIL]  !` row naming that
    name, the half of the count a list of verdicts alone cannot see.

    The planted list goes in through `_run_controls`'s own `controls`
    parameter and out through `selfcheck`, so what is measured is the real
    walk, the real guard and the real tally rather than a copy of them. With
    no manifest, no census control runs after the walk.
    """
    def passing(name: str) -> Controls:
        def entry(check_row: CheckRow, _skip_row: SkipRow) -> None:
            check_row(f"{name}  (inner)", True, ACTUAL + "fine")
        return _planted_entry(name, entry)

    def refusing(_check_row: CheckRow, _skip_row: SkipRow) -> None:
        raise Refusal("a planted refusal out of one self-test",
                      next="nothing — this is arm nnnnn's own plant, and the "
                      "rows after it are the point.")

    def raising(_check_row: CheckRow, _skip_row: SkipRow) -> None:
        raise ImportError("a planted ImportError, on no list anywhere")

    seen: dict[str, tuple[int, int, bool, bool, bool, bool]] = {}
    for why, middle, worded in (("a Refusal", refusing, "REFUSED instead"),
                                ("an ImportError", raising, "raised instead")):
        buffer = io.StringIO()
        planted = [passing("nnnnn-first"),
                   _planted_entry("nnnnn-middle", middle),
                   passing("nnnnn-last")]
        code = selfcheck(buffer, None,
                         functools.partial(_run_controls, controls=planted))
        text = buffer.getvalue()
        lines = text.splitlines()
        bangs = [line for line in lines if line.startswith("  [FAIL]  !")]
        seen[why] = (code, len(bangs),
                     "nnnnn-first  (inner)" in text,
                     "nnnnn-last  (inner)" in text,
                     len(bangs) == 1 and "nnnnn-middle" in bangs[0]
                     and worded in bangs[0],
                     "REFUSED after row" in text)
    def halved(check_row: CheckRow, skip_row: SkipRow) -> None:
        check_row("nnnnn-half  (inner)", True, ACTUAL + "fine")
        skip_row("nnnnn-half  (inner) the half not exercised",
                 "a planted SKIP beside the verdict of its own arm.")

    # Two entries whose rows open with one name, between two that do not,
    # and an entry whose verdict and SKIP share its name: every row prints,
    # and the walk ends in ONE `!` row, naming the two entries' name alone.
    buffer = io.StringIO()
    code = selfcheck(buffer, None, functools.partial(
        _run_controls, controls=[passing("nnnnn-first"),
                                 passing("nnnnn-twice"),
                                 passing("nnnnn-twice"),
                                 _planted_entry("nnnnn-half", halved),
                                 passing("nnnnn-last")]))
    text = buffer.getvalue()
    bangs = [line for line in text.splitlines()
             if line.startswith("  [FAIL]  !")]
    seen["two rows of one name"] = (
        code, len(bangs), "nnnnn-first  (inner)" in text,
        "nnnnn-last  (inner)" in text,
        len(bangs) == 1 and "nnnnn-twice opens more than one row" in bangs[0]
        and "nnnnn-half" not in bangs[0]
        and text.count("nnnnn-twice  (inner)") == 2,
        "REFUSED after row" in text)
    def skipping(check_row: CheckRow, skip_row: SkipRow) -> None:
        skip_row("nnnnn-skipped  (inner)", "a planted SKIP under a name "
                 "another entry SKIPs under too.")

    # Two entries that each SKIP under one name, between two that pass: both
    # SKIPs print, and the walk ends in ONE `!` row naming that name.
    buffer = io.StringIO()
    code = selfcheck(buffer, None, functools.partial(
        _run_controls, controls=[passing("nnnnn-first"),
                                 _planted_entry("nnnnn-skipped", skipping),
                                 _planted_entry("nnnnn-skipped", skipping),
                                 passing("nnnnn-last")]))
    text = buffer.getvalue()
    bangs = [line for line in text.splitlines()
             if line.startswith("  [FAIL]  !")]
    seen["two SKIPs of one name"] = (
        code, len(bangs), "nnnnn-first  (inner)" in text,
        "nnnnn-last  (inner)" in text,
        len(bangs) == 1 and "nnnnn-skipped opens more than one row" in bangs[0]
        and text.count("nnnnn-skipped  (inner)") == 2,
        "REFUSED after row" in text)
    ok = all(code == 1 and count == 1 and first and last and named
             and not stopped
             for code, count, first, last, named, stopped in seen.values())
    check("nnnnn  a self-test that REFUSES or raises instead of reporting a "
          "verdict costs exactly one `[FAIL]  !` row naming it and saying "
          "which it did, and every "
          "self-test after it still runs: a planted list of three entries, "
          "walked once with a `Refusal` in the middle and once with an "
          "ImportError, prints both outer rows both times, exits 1 and never "
          "2, and its tally never says `REFUSED after row` — a refusal out "
          "of ONE self-test is not a statement about the run, and the rows "
          "after it are what a reader loses when it is treated as one; and "
          "two rows that open with one name, walked between two that do "
          "not, both print and cost one `[FAIL]  !` row naming that name, "
          "as two SKIPs that open with one name do, while one arm's verdict "
          "and its SKIP under one name cost none",
          ok,
          ACTUAL + "; ".join(
              f"{why} in the middle -> exit {code}, {count} [FAIL] ! row(s), "
              f"first row {first}, last row {last}, the row names the middle "
              f"entry as it ended {named}, tally says REFUSED after row "
              f"{stopped}"
              for why, (code, count, first, last, named, stopped)
              in seen.items()),
          next="Guard each entry of the walk in `_run_controls`, not the "
               "walk: one self-test's missing tool must not be reported as a "
               "refusal of every self-test after it.")


def _raise_control(check: CheckRow) -> None:
    """(s) the catch a control's fault travels through is CLOSED. Both exits
    are exercised, because they mean different things."""
    def raising(check_row: CheckRow, _skip_row: SkipRow) -> None:
        check_row("(inner) an arm that ran before the fault", True,
                  ACTUAL + "fine")
        raise ImportError("a planted ImportError, on no list anywhere")

    def refusing(check_row: CheckRow, _skip_row: SkipRow) -> None:
        check_row("(inner) an arm that ran before the refusal", True,
                  ACTUAL + "fine")
        raise Refusal("a planted refusal",
                      next="nothing — this is control (s)'s own plant, and the rows above it are "
                      "the point: the arms that ran before a refusal still print.")

    fail_buf, refuse_buf = io.StringIO(), io.StringIO()
    fail_code = selfcheck(fail_buf, None, raising)
    refuse_code = selfcheck(refuse_buf, None, refusing)
    fail, refuse = fail_buf.getvalue(), refuse_buf.getvalue()
    check("s  a control raising something no enumerated tuple listed "
          "(ImportError) is a [FAIL] ! row and exit 1, a control raising "
          "Refusal is the REFUSED line and exit 2 with a tally that says "
          "where it stopped, and in both the arms that ran before the fault "
          "are still printed",
          fail_code == 1 and "[FAIL]  !" in fail
          and "ImportError: a planted ImportError" in fail
          and "an arm that ran before the fault" in fail
          and refuse_code == 2 and "REFUSED: a planted refusal" in refuse
          and "[FAIL]" not in refuse
          and "an arm that ran before the refusal" in refuse
          and "1/1 passed, REFUSED after row 1" in refuse,
          f"{ACTUAL}ImportError -> exit {fail_code}, "
          f"{fail.count('  [PASS]')} arm(s) printed before it, [FAIL] ! "
          f"row={'[FAIL]  !' in fail}; Refusal -> exit {refuse_code}, "
          f"{refuse.count('  [PASS]')} arm(s) printed before it, REFUSED "
          f"line={'REFUSED: a planted refusal' in refuse}, tally "
          + next((line.strip() for line in refuse.splitlines()
                  if " passed" in line), "(none)") + "")


#: `N/M passed` at the head of a line, wherever the tally is printed.
#: The quiet shape carries the banner's words before `passed` (`3/3 census
#: controls passed`); the loud shape carries none.
_TALLY_LINE = re.compile(r"^\s*\d+/\d+ (?:[a-z][a-z -]* )?passed")


def _tally_at(lines: list[str]) -> int:
    """The index of the tally line in `lines`, or -1."""
    return next((number for number, line in enumerate(lines)
                 if _TALLY_LINE.match(line)), -1)


def _pass_rows(lines: list[str]) -> list[str]:
    """Every `[PASS]` ROW of a block. A row's label may quote the word — arm
    `aaaa`'s does — so the question "did this block print a passing row" is
    asked of line openings and never of the whole text."""
    return [line for line in lines if line.startswith("  [PASS]")]


def _quiet_pass_control(check: CheckRow, skip: SkipRow) -> None:
    """(aaaa) the block nobody asked for prints its VERDICT and stands aside;
    the one a reader asks for by name prints the whole block.

    Three measurements of one rule, and the third is the one that matters. A
    planted control set run both ways says what the two shapes ARE. A real
    `capture`, whose census carries a pin its own control cannot prove, says
    what a reader meets when a control goes red in front of the command they
    typed: the failing row, the tally, then the refusal that stops it — and
    no page of PASS rows between the command and the answer.

    The real `capture` inside this arm runs the census's controls and nothing
    of this file: `cli.main` calls `census_check` in front of a capture, and
    `census_check` reaches `manifest_controls` alone, so no arm — this one
    included — runs a second time inside the run it measures.
    """
    label = ("aaaa  the census controls that PRECEDE a command print their "
             "verdict alone — the failing rows, the tally, the disclosed "
             "SKIPs, no [PASS] row and no banner — while `--selfcheck` asked "
             "for by name prints the whole block; and a real `capture` whose "
             "census carries an unproven pin prints that failing row, the "
             "tally and then the refusal that stops the command, in that "
             "order, with nothing of the capture started — and that refusal's "
             "`next:` line names `census --manifest M`, the command that "
             "prints its state block under those same controls")

    def planted(check_row: CheckRow, skip_row: SkipRow) -> None:
        check_row("(inner) an arm that passed", True, ACTUAL + "fine")
        check_row("(inner) an arm that FAILED", False, ACTUAL + "a planted red",
                  next="nothing — this is arm aaaa's own plant, and the shape "
                       "of the block around it is the point.")
        skip_row("(inner) an arm this machine cannot exercise",
                 "a planted SKIP: a disclosed SKIP never vanishes into a pass, "
                 "quiet or loud.")

    quiet_buf, loud_buf = io.StringIO(), io.StringIO()
    quiet_code = selfcheck(quiet_buf, None, planted, quiet=True)
    loud_code = selfcheck(loud_buf, None, planted)
    quiet, loud = quiet_buf.getvalue(), loud_buf.getvalue()
    quiet_lines = [line for line in quiet.splitlines() if line.strip()]
    red = next((number for number, line in enumerate(quiet_lines)
                if line.startswith("  [FAIL]")), -1)
    tally = _tally_at(quiet_lines)
    skipped = next((number for number, line in enumerate(quiet_lines)
                    if line.startswith("  [SKIP]")), -1)
    # ROWS, not the word: a row's own label may quote `[PASS]` — this one
    # does — and a search of the whole text would then find what it planted.
    quiet_passes = len(_pass_rows(quiet_lines))
    shapes = (quiet_code == 1 and loud_code == 1
              and not quiet_passes and "=====" not in quiet
              and red == 0 and 0 < tally < skipped
              and "a planted red" in quiet
              and bool(_pass_rows(loud.splitlines()))
              and "GOLDEN-CENSUS SELF-CHECK" in loud)

    with _box("golden-census-quiet-") as box:
        manifest_path = _scratch(box, census_text=_STUB_CENSUS + _UNPROVEN_PIN)
        code, text = _quietly(main, ["capture", "--manifest", manifest_path,
                                     "--out", os.path.join(box, "out")])
    lines = [line for line in text.splitlines() if line.strip()]
    opener = lines[0] if lines else ""
    reds = [line for line in lines if line.startswith("  [FAIL]")]
    live_tally = _tally_at(lines)
    refused = next((number for number, line in enumerate(lines)
                    if line.lstrip().startswith("REFUSED: ")), -1)
    if "GOLDEN_CENSUS_UNREAD" not in text:
        # The planted control never got to run: something ahead of the census
        # controls raised a `Refusal` and the block stopped there. That is a
        # statement about this copy of golden-census, not about the quiet
        # shape, and an arm whose measurement did not happen is a disclosed
        # SKIP rather than a red row about something it never saw.
        skip(label, "the planted census control never ran: the block in "
                    "front of the command stopped at an earlier control "
                    f"({_one_line(lines[-1] if lines else '(no output)', 160)}"
                    "). Nothing is claimed about the quiet shape here.")
        return
    # The planted row is asserted PRESENT and not counted alone: this run is a
    # whole block of the census's controls, and any other row that went red
    # belongs on the page beside it. A count here would make this arm a second
    # alarm for every red row in that census.
    # The sentence a reader is sent to, asserted as the bytes they read: a
    # refusal that sent them back to the red block they had just been shown
    # would tell them nothing, and `census` — the command that prints the
    # environment those controls are about — belongs in the sentence and not
    # in a code comment.
    next_names_census = any(
        line.lstrip().startswith("next: ") and "`census --manifest M`" in line
        for line in lines)
    live = (code == 2 and opener.startswith("process group ")
            and not _pass_rows(lines) and "=====" not in text
            and bool(reds) and "UNPROVEN" in text
            and "GOLDEN_CENSUS_UNREAD" in text
            and 0 < live_tally < refused
            and next_names_census
            and "capture complete" not in text)
    check(label, shapes and live,
          f"{ACTUAL}planted quiet -> exit {quiet_code}, "
          f"{len(quiet_lines)} line(s), FAIL row at {red}, tally at {tally}, "
          f"SKIP at {skipped}, {quiet_passes} PASS row(s); planted "
          f"loud -> exit {loud_code}, {len(loud.splitlines())} line(s), "
          f"banner present={'GOLDEN-CENSUS SELF-CHECK' in loud}, "
          f"{len(_pass_rows(loud.splitlines()))} PASS row(s); a real "
          f"`capture` over an unproven pin "
          f"-> exit {code}, opened {_one_line(opener, 60)!r}, {len(reds)} "
          f"[FAIL] row(s), {len(_pass_rows(lines))} PASS row(s), tally at "
          f"{live_tally}, REFUSED at {refused}, "
          f"the refusal's next: names census={next_names_census}, "
          f"capture started={'capture complete' in text}",
          next="`cli.main` is the one caller that asks for a quiet block, and "
               "`core.Report` is the one printer that decides what quiet "
               "means; the order is the failing rows, the tally, the SKIPs, "
               "and the refusal the caller writes under them.")


# ------------------------------------------------------- the self-check
#
# `selfcheck` is the second entry point onto `controls.block`; the comment
# above `block` says what the two share and what tells them apart.


def selfcheck(out: Any, manifest: Manifest | None = None,
              controls: Controls | None = None, quiet: bool = False) -> int:
    """golden-census's OWN arms — every guard shipped with the planted case
    that proves it can go red — and, when a manifest is given, that census's
    controls under them.

    What a reader asks for BY NAME. These arms are regression tests of code
    that does not move between one command of a reader's and the next, so they
    run where they are asked for — `--selfcheck`, `--selftest`, and the
    install check — and in front of nothing.

    `quiet` is handed straight to the block and decided nowhere else: WHICH
    controls run is this function's business, WHAT is printed is
    `core.Report`'s.

    A work directory of the census's controls that stayed is named after the
    block, beside its tally: the line is held until the block is printed.
    """
    left = io.StringIO()
    code = block(out, "GOLDEN-CENSUS SELF-CHECK", quiet,
                 controls or functools.partial(_run_controls,
                                               manifest=manifest, out=left))
    out.write(left.getvalue())
    return code

