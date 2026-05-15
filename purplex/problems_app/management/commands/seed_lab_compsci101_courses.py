"""
Management command to seed the six COMPSCI101A-F lab courses.

Designed for Kaitlin Riegel / Andrew Luxton-Reilly / Paul Denny's
Auckland Compsci101 hint-mechanism study, week of 2026-05-18.

The experiment uses a Latin square across three hint mechanisms
(Variable Fade, Subgoal Highlighting, Suggested Trace) on Tasks 2-4.
CodeRunner randomly assigns each student to one of COMPSCI101A..F;
the student joins that course on purplex.org and sees six problems with
the hint ordering dictated by their condition.

Prerequisite: `seed_demo_set_data` must have run first - this command
sources content from the six `demo-*` problems and clones them into a
fresh `lab-*` namespace. No `demo-*` row is mutated.

Idempotent: safe to re-run via get_or_create.
"""

from django.core.management.base import BaseCommand

from purplex.config.environment import config

# ----------------------------------------------------------------------
# Latin-square assignment (Tasks 2-4 only)
# ----------------------------------------------------------------------
# Each row is (task2_mechanism, task3_mechanism, task4_mechanism).
# Each (task, mechanism) pair appears in exactly two of the six courses.
LATIN_SQUARE = {
    "A": ("vf", "sh", "st"),
    "B": ("vf", "st", "sh"),
    "C": ("sh", "vf", "st"),
    "D": ("sh", "st", "vf"),
    "E": ("st", "vf", "sh"),
    "F": ("st", "sh", "vf"),
}

MECHANISM_TO_HINT_TYPE = {
    "vf": "variable_fade",
    "sh": "subgoal_highlight",
    "st": "suggested_trace",
}

MECHANISM_DISPLAY = {
    "vf": "VF",
    "sh": "SH",
    "st": "ST",
}

# ----------------------------------------------------------------------
# Source-to-task mapping (committed default - see plan)
# ----------------------------------------------------------------------
# Tasks 2-4 source from the three EiPL problems (they already have hints
# defined in seed_demo_set_data). Tasks 1, 5, 6 source from Prompt problems.
TASK_SOURCES = {
    1: "demo-count-negatives",  # Prompt, warm-up, all hints on
    2: "demo-check-sorted",  # EiPL,   variable hint (vf/sh/st)
    3: "demo-longest-run",  # EiPL,   variable hint (vf/sh/st)
    4: "demo-sum-of-squares",  # EiPL,   variable hint (vf/sh/st)
    5: "demo-count-fixed-points",  # Prompt, free choice, all hints on
    6: "demo-sort-sublist",  # Prompt, free choice, all hints on
}

VARIABLE_HINT_TASKS = {2, 3, 4}
SHARED_TASKS = {1, 5, 6}


# ----------------------------------------------------------------------
# Hint content for the three Prompt sources (Tasks 1, 5, 6).
# The Prompt source rows have no ProblemHint records in the demo seed,
# so we author them here. Copied into every shared clone.
# Content shape mirrors seed_demo_set_data.py:525-664.
# ----------------------------------------------------------------------
PROMPT_HINT_CONTENT = {
    "demo-count-negatives": {
        "variable_fade": {
            "mappings": [
                {"from": "count", "to": "running tally"},
                {"from": "x", "to": "current element"},
            ]
        },
        "subgoal_highlight": {
            "subgoals": [
                {
                    "line_start": 2,
                    "line_end": 2,
                    "title": "Initialize counter",
                    "explanation": "Start a tally at zero.",
                },
                {
                    "line_start": 3,
                    "line_end": 5,
                    "title": "Tally negatives",
                    "explanation": (
                        "Walk through each element; whenever it is negative, "
                        "bump the tally."
                    ),
                },
                {
                    "line_start": 6,
                    "line_end": 6,
                    "title": "Return total",
                    "explanation": "Return the tally.",
                },
            ]
        },
        "suggested_trace": {
            "suggested_call": "process_list([13, -2, -53, 32, -23, -1, 0])",
        },
    },
    "demo-count-fixed-points": {
        "variable_fade": {
            "mappings": [
                {"from": "count", "to": "running tally"},
                {"from": "i", "to": "current index"},
                {"from": "lst[i]", "to": "element at current index"},
            ]
        },
        "subgoal_highlight": {
            "subgoals": [
                {
                    "line_start": 2,
                    "line_end": 2,
                    "title": "Initialize counter",
                    "explanation": "Start a tally at zero.",
                },
                {
                    "line_start": 3,
                    "line_end": 5,
                    "title": "Count fixed points",
                    "explanation": (
                        "Walk through each index; whenever the element at that "
                        "index equals the index itself, bump the tally."
                    ),
                },
                {
                    "line_start": 6,
                    "line_end": 6,
                    "title": "Return total",
                    "explanation": "Return the tally.",
                },
            ]
        },
        "suggested_trace": {
            "suggested_call": "process_list([0, 1, 2, 3])",
        },
    },
    "demo-sort-sublist": {
        "variable_fade": {
            "mappings": [
                {"from": "result", "to": "working copy of the list"},
                {"from": "start", "to": "start of slice (inclusive)"},
                {"from": "end", "to": "end of slice (inclusive)"},
            ]
        },
        "subgoal_highlight": {
            "subgoals": [
                {
                    "line_start": 2,
                    "line_end": 2,
                    "title": "Copy input",
                    "explanation": (
                        "Make a working copy so the original list is unchanged."
                    ),
                },
                {
                    "line_start": 3,
                    "line_end": 3,
                    "title": "Sort the slice",
                    "explanation": (
                        "Replace the slice from start to end (inclusive) with "
                        "its sorted version."
                    ),
                },
                {
                    "line_start": 4,
                    "line_end": 4,
                    "title": "Return result",
                    "explanation": "Return the modified copy.",
                },
            ]
        },
        "suggested_trace": {
            "suggested_call": "process_list([7, 9, 3, 6, 1], 1, 3)",
        },
    },
}


# ----------------------------------------------------------------------
# Segmentation examples per source slug.
# Required by services/segmentation_service.py:215-331 - injected into the
# few-shot prompt for the AI segmentation request.
# Rules enforced by Verification step 3:
#   - multi_structural: strict 1:1 line mapping (each segment -> exactly 1 line)
#   - No line overlaps across multi_structural segments
#   - Every segments[i] is a verbatim substring of the prompt
#   - multi_structural has > threshold (2) segments
#   - relational has exactly 1 segment, may span multiple lines
# ----------------------------------------------------------------------
SEGMENTATION_EXAMPLES = {
    # Task 1: demo-count-negatives
    "demo-count-negatives": {
        "relational": {
            "prompt": "It counts how many negative numbers are in the list",
            "segments": ["It counts how many negative numbers are in the list"],
            "code_lines": [[2, 3, 4, 5, 6]],
        },
        "multi_structural": {
            "prompt": (
                "It starts a counter at zero, loops through each element, "
                "checks if it is negative, increments the counter, "
                "returns the total"
            ),
            "segments": [
                "It starts a counter at zero",
                "loops through each element",
                "checks if it is negative",
                "increments the counter",
                "returns the total",
            ],
            "code_lines": [[2], [3], [4], [5], [6]],
        },
    },
    # Task 2: demo-check-sorted
    "demo-check-sorted": {
        "relational": {
            "prompt": "It checks whether the list is sorted in non-decreasing order",
            "segments": [
                "It checks whether the list is sorted in non-decreasing order"
            ],
            "code_lines": [[2, 3, 4, 5]],
        },
        "multi_structural": {
            "prompt": (
                "It loops through pairs of adjacent indices, "
                "checks if the current element is greater than the next, "
                "returns False if so, "
                "returns True otherwise"
            ),
            "segments": [
                "It loops through pairs of adjacent indices",
                "checks if the current element is greater than the next",
                "returns False if so",
                "returns True otherwise",
            ],
            "code_lines": [[2], [3], [4], [5]],
        },
    },
    # Task 3: demo-longest-run (13 lines, pick 6 distinct named actions)
    "demo-longest-run": {
        "relational": {
            "prompt": (
                "It returns the length of the longest run of equal consecutive elements"
            ),
            "segments": [
                "It returns the length of the longest run of equal consecutive elements"
            ],
            "code_lines": [[2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]],
        },
        "multi_structural": {
            "prompt": (
                "It initializes the best run length to one, "
                "initializes the current run length to one, "
                "walks through each subsequent index, "
                "checks whether the element matches the previous one, "
                "increases the current run length on a match, "
                "returns the best run length"
            ),
            "segments": [
                "It initializes the best run length to one",
                "initializes the current run length to one",
                "walks through each subsequent index",
                "checks whether the element matches the previous one",
                "increases the current run length on a match",
                "returns the best run length",
            ],
            "code_lines": [[4], [5], [6], [7], [8], [13]],
        },
    },
    # Task 4: demo-sum-of-squares
    "demo-sum-of-squares": {
        "relational": {
            "prompt": "It returns the sum of the squares of the numbers",
            "segments": ["It returns the sum of the squares of the numbers"],
            "code_lines": [[2, 3, 4, 5]],
        },
        "multi_structural": {
            "prompt": (
                "It initializes a running total at zero, "
                "loops through each number, "
                "adds its square to the total, "
                "returns the total"
            ),
            "segments": [
                "It initializes a running total at zero",
                "loops through each number",
                "adds its square to the total",
                "returns the total",
            ],
            "code_lines": [[2], [3], [4], [5]],
        },
    },
    # Task 5: demo-count-fixed-points
    "demo-count-fixed-points": {
        "relational": {
            "prompt": "It counts elements that equal their own index",
            "segments": ["It counts elements that equal their own index"],
            "code_lines": [[2, 3, 4, 5, 6]],
        },
        "multi_structural": {
            "prompt": (
                "It initializes a counter, "
                "loops over each index, "
                "checks if the element equals the index, "
                "increments the counter, "
                "returns the count"
            ),
            "segments": [
                "It initializes a counter",
                "loops over each index",
                "checks if the element equals the index",
                "increments the counter",
                "returns the count",
            ],
            "code_lines": [[2], [3], [4], [5], [6]],
        },
    },
    # Task 6: demo-sort-sublist
    "demo-sort-sublist": {
        "relational": {
            "prompt": (
                "It returns a copy of the list with the slice from start to end sorted"
            ),
            "segments": [
                "It returns a copy of the list with the slice from start to end sorted"
            ],
            "code_lines": [[2, 3, 4]],
        },
        "multi_structural": {
            "prompt": (
                "It makes a copy of the list, "
                "sorts the slice from start to end in place, "
                "returns the modified copy"
            ),
            "segments": [
                "It makes a copy of the list",
                "sorts the slice from start to end in place",
                "returns the modified copy",
            ],
            "code_lines": [[2], [3], [4]],
        },
    },
}


class Command(BaseCommand):
    help = (
        "Seeds six COMPSCI101A-F lab courses with Latin-squared hint mechanisms "
        "on Tasks 2-4. Prerequisite: seed_demo_set_data must have run first."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force creation even in non-development environment",
        )
        parser.add_argument(
            "--instructor",
            default="instructor",
            help="Username of the primary instructor for all six courses",
        )
        parser.add_argument(
            "--co-instructor",
            action="append",
            default=[],
            metavar="USERNAME",
            help=(
                "Additional username to add as primary instructor on all six "
                "courses. Repeatable. Skipped with a warning if user is missing."
            ),
        )

    def handle(self, *args, **options):
        if not config.is_development and not options["force"]:
            self.stdout.write(
                self.style.ERROR(
                    "Lab seed data can only be created in development "
                    "environment.\nUse --force to override this check."
                )
            )
            return

        if not config.is_development:
            self.stdout.write(
                self.style.WARNING(
                    "WARNING: Seeding lab data in non-development environment!"
                )
            )

        from datetime import datetime

        from django.contrib.auth.models import User
        from django.db import transaction
        from django.utils import timezone

        from purplex.problems_app.models import (
            Course,
            CourseInstructor,
            CourseInstructorRole,
            CourseProblemSet,
            EiplProblem,
            Problem,
            ProblemHint,
            ProblemSet,
            ProblemSetMembership,
            PromptProblem,
            TestCase,
        )

        # ------------------------------------------------------------------
        # Look up primary instructor
        # ------------------------------------------------------------------
        try:
            instructor = User.objects.get(username=options["instructor"])
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f"User '{options['instructor']}' not found. "
                    "Create the user first or pass --instructor <username>."
                )
            )
            return

        # ------------------------------------------------------------------
        # Look up co-instructors (optional, repeatable)
        # ------------------------------------------------------------------
        co_instructors = []
        missing_co_instructors = []
        for username in options["co_instructor"]:
            try:
                co_instructors.append(User.objects.get(username=username))
            except User.DoesNotExist:
                missing_co_instructors.append(username)
                self.stdout.write(
                    self.style.WARNING(
                        f"  Co-instructor '{username}' not found - skipping. "
                        "Create the user later and re-run to add them."
                    )
                )

        # ------------------------------------------------------------------
        # Sanity-check that all six source problems exist
        # ------------------------------------------------------------------
        source_problems: dict[int, Problem] = {}
        for task_num, source_slug in TASK_SOURCES.items():
            try:
                source_problems[task_num] = Problem.objects.get(slug=source_slug)
            except Problem.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(
                        f"Source problem '{source_slug}' (Task {task_num}) not "
                        "found. Run `python manage.py seed_demo_set_data` first."
                    )
                )
                return

        # All mutations below run inside a single transaction so a partial
        # failure leaves no half-built state behind.
        with transaction.atomic():
            self._seed(
                instructor=instructor,
                co_instructors=co_instructors,
                source_problems=source_problems,
                Course=Course,
                CourseInstructor=CourseInstructor,
                CourseInstructorRole=CourseInstructorRole,
                CourseProblemSet=CourseProblemSet,
                EiplProblem=EiplProblem,
                ProblemHint=ProblemHint,
                ProblemSet=ProblemSet,
                ProblemSetMembership=ProblemSetMembership,
                PromptProblem=PromptProblem,
                TestCase=TestCase,
                timezone=timezone,
                datetime=datetime,
            )

        # ------------------------------------------------------------------
        # Summary (outside the transaction; safe to render after commit)
        # ------------------------------------------------------------------
        self._print_summary(instructor, co_instructors, missing_co_instructors)

    def _seed(
        self,
        *,
        instructor,
        co_instructors,
        source_problems,
        Course,
        CourseInstructor,
        CourseInstructorRole,
        CourseProblemSet,
        EiplProblem,
        ProblemHint,
        ProblemSet,
        ProblemSetMembership,
        PromptProblem,
        TestCase,
        timezone,
        datetime,
    ):
        """Mutating work — runs inside transaction.atomic()."""
        # ------------------------------------------------------------------
        # 1. Clone problems
        # ------------------------------------------------------------------
        # task_clones[(task_num, mechanism_or_None)] -> cloned Problem
        # Shared tasks key mechanism as None; variable tasks key by "vf"/"sh"/"st".
        task_clones = {}

        for task_num, source in source_problems.items():
            if task_num in SHARED_TASKS:
                clone = self._clone_problem(
                    source=source,
                    slug=f"lab-task{task_num}",
                    title_suffix="",
                    instructor=instructor,
                    EiplProblem=EiplProblem,
                    PromptProblem=PromptProblem,
                )
                task_clones[(task_num, None)] = clone
                self._copy_test_cases(source, clone, TestCase)
                self._create_all_hints(clone, source, ProblemHint)
            else:
                for mechanism in ("vf", "sh", "st"):
                    clone = self._clone_problem(
                        source=source,
                        slug=f"lab-task{task_num}-{mechanism}",
                        title_suffix=f" ({MECHANISM_DISPLAY[mechanism]})",
                        instructor=instructor,
                        EiplProblem=EiplProblem,
                        PromptProblem=PromptProblem,
                    )
                    task_clones[(task_num, mechanism)] = clone
                    self._copy_test_cases(source, clone, TestCase)
                    self._create_single_hint(clone, source, mechanism, ProblemHint)

        # ------------------------------------------------------------------
        # 2. Build six problem sets + memberships
        # ------------------------------------------------------------------
        problem_sets: dict[str, ProblemSet] = {}
        for letter, (m2, m3, m4) in LATIN_SQUARE.items():
            slug = f"lab-compsci101-{letter.lower()}"
            ps, created = ProblemSet.objects.get_or_create(
                slug=slug,
                defaults={
                    "title": f"COMPSCI101 Lab (Group {letter})",
                    "description": (
                        "Auckland Compsci101 hint-mechanism study lab. "
                        f"Group {letter}: Task 2 = {MECHANISM_DISPLAY[m2]}, "
                        f"Task 3 = {MECHANISM_DISPLAY[m3]}, "
                        f"Task 4 = {MECHANISM_DISPLAY[m4]}."
                    ),
                    "is_public": True,
                    "created_by": instructor,
                },
            )
            self._report("ProblemSet", slug, created)
            problem_sets[letter] = ps

            ordered_clones = [
                task_clones[(1, None)],
                task_clones[(2, m2)],
                task_clones[(3, m3)],
                task_clones[(4, m4)],
                task_clones[(5, None)],
                task_clones[(6, None)],
            ]
            for idx, clone in enumerate(ordered_clones):
                _, m_created = ProblemSetMembership.objects.get_or_create(
                    problem_set=ps,
                    problem=clone,
                    defaults={"order": idx},
                )
                self._report(
                    "ProblemSetMembership", f"{slug} -> {clone.slug}", m_created
                )

        # ------------------------------------------------------------------
        # 3. Six courses + instructor + problem set link
        # ------------------------------------------------------------------
        # Due date: week after the planned 2026-05-18 lab.
        due_date = timezone.make_aware(datetime(2026, 5, 25, 23, 59, 59))

        for letter, ps in problem_sets.items():
            course_id = f"COMPSCI101{letter}"
            course, created = Course.all_objects.get_or_create(
                course_id=course_id,
                defaults={
                    "name": f"COMPSCI101 (Lab Group {letter})",
                    "description": (
                        "Compsci101 hint-mechanism study lab. Auckland 2026-05-18."
                    ),
                    "is_active": True,
                    "enrollment_open": True,
                },
            )
            self._report("Course", course_id, created)

            # If a previously soft-deleted course of this id exists, revive it.
            # `defaults` only applies on create, so a stale soft-deleted row
            # would otherwise stay hidden after get_or_create returns it.
            if not created and course.is_deleted:
                course.is_deleted = False
                course.deleted_at = None
                course.is_active = True
                course.enrollment_open = True
                course.save(
                    update_fields=[
                        "is_deleted",
                        "deleted_at",
                        "is_active",
                        "enrollment_open",
                        "updated_at",
                    ]
                )
                self.stdout.write(
                    self.style.WARNING(f"  Revived soft-deleted Course: {course_id}")
                )

            # Primary instructor
            _, ci_created = CourseInstructor.objects.get_or_create(
                course=course,
                user=instructor,
                defaults={
                    "role": CourseInstructorRole.PRIMARY,
                    "added_by": instructor,
                },
            )
            self._report(
                "CourseInstructor",
                f"{instructor.username} -> {course_id}",
                ci_created,
            )

            # Co-instructors (idempotent; existing rows are left untouched)
            for co in co_instructors:
                _, co_created = CourseInstructor.objects.get_or_create(
                    course=course,
                    user=co,
                    defaults={
                        "role": CourseInstructorRole.PRIMARY,
                        "added_by": instructor,
                    },
                )
                self._report(
                    "CourseInstructor",
                    f"{co.username} -> {course_id}",
                    co_created,
                )

            # Link the matching problem set. get_or_create preserves any manual
            # edits to due_date / deadline_type / is_required between runs.
            # update_or_create would silently revert them.
            _, cps_created = CourseProblemSet.objects.get_or_create(
                course=course,
                problem_set=ps,
                defaults={
                    "order": 1,
                    "due_date": due_date,
                    "deadline_type": "soft",
                    "is_required": True,
                },
            )
            self._report("CourseProblemSet", f"{ps.slug} -> {course_id}", cps_created)

    # ----------------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------------

    def _print_summary(self, instructor, co_instructors, missing_co_instructors):
        """Render the human-readable summary after the seed transaction commits."""
        course_ids = [f"COMPSCI101{letter}" for letter in LATIN_SQUARE]
        summary_lines = [
            "\nLab seed data ready!",
            f"  Courses:        {', '.join(course_ids)}",
            f"  Problem clones: 12 ({len(SHARED_TASKS)} shared + "
            f"{len(VARIABLE_HINT_TASKS) * 3} per-mechanism)",
            "  Problem sets:   6 (lab-compsci101-a through -f)",
            f"  Primary inst.:  {instructor.username}",
        ]
        if co_instructors:
            summary_lines.append(
                f"  Co-instructors: {', '.join(c.username for c in co_instructors)}"
            )
        if missing_co_instructors:
            summary_lines.append(
                self.style.WARNING(
                    f"  Missing users:  {', '.join(missing_co_instructors)} "
                    "(re-run after creating them)"
                )
            )
        summary_lines.append("  Due date:       2026-05-25 23:59:59")
        summary_lines.append("")
        summary_lines.append("  Latin square (Task 2 / Task 3 / Task 4):")
        for letter, (m2, m3, m4) in LATIN_SQUARE.items():
            summary_lines.append(
                f"    COMPSCI101{letter}: "
                f"{MECHANISM_DISPLAY[m2]} / "
                f"{MECHANISM_DISPLAY[m3]} / "
                f"{MECHANISM_DISPLAY[m4]}"
            )
        self.stdout.write(self.style.SUCCESS("\n".join(summary_lines)))

    def _clone_problem(
        self,
        source,
        slug: str,
        title_suffix: str,
        instructor,
        EiplProblem,
        PromptProblem,
    ):
        """Create a lab-* clone of a source problem, with segmentation forced on.

        Returns the cloned Problem (subclass instance). Idempotent via slug.
        """
        from purplex.problems_app.models import EiplProblem as _EiplProblem
        from purplex.problems_app.models import PromptProblem as _PromptProblem

        # Pre-check for an existing clone before constructing the defaults dict.
        existing = (
            _EiplProblem.objects.filter(slug=slug).first()
            or _PromptProblem.objects.filter(slug=slug).first()
        )
        if existing:
            self._report(type(existing).__name__, slug, False)
            return existing

        seg_config = {
            "enabled": True,
            "threshold": 2,
            "examples": SEGMENTATION_EXAMPLES[source.slug],
        }
        common_fields = {
            "title": source.title + title_suffix,
            "description": source.description,
            "function_signature": source.function_signature,
            "function_name": source.function_name,
            "reference_solution": source.reference_solution,
            "difficulty": source.difficulty,
            "memory_limit": source.memory_limit,
            "llm_config": dict(source.llm_config) if source.llm_config else {},
            "completion_threshold": source.completion_threshold,
            "max_attempts": source.max_attempts,
            "tags": list(source.tags) if source.tags else [],
            "is_active": True,
            "created_by": instructor,
            # Force segmentation on for every clone (overrides PromptProblem's
            # SEGMENTATION_DEFAULT_ENABLED = False).
            "requires_highlevel_comprehension": True,
            "segmentation_config": seg_config,
            "segmentation_threshold": 2,
        }

        if isinstance(source, _PromptProblem):
            clone = _PromptProblem.objects.create(
                slug=slug,
                display_mode=source.display_mode,
                display_data=dict(source.display_data) if source.display_data else {},
                image_url=source.image_url,
                image_alt_text=source.image_alt_text,
                **common_fields,
            )
            self._report("PromptProblem", slug, True)
        elif isinstance(source, _EiplProblem):
            clone = _EiplProblem.objects.create(slug=slug, **common_fields)
            self._report("EiplProblem", slug, True)
        else:
            raise ValueError(
                f"Unsupported source problem type {type(source).__name__} "
                f"for slug {source.slug}"
            )

        # M2M: categories and prerequisites
        clone.categories.set(source.categories.all())
        clone.prerequisites.set(source.prerequisites.all())
        return clone

    def _copy_test_cases(self, source, clone, TestCase):
        """Copy every TestCase row from source to clone. Idempotent."""
        for tc in source.test_cases.all():
            _, created = TestCase.objects.get_or_create(
                problem=clone,
                inputs=tc.inputs,
                expected_output=tc.expected_output,
                defaults={
                    "is_sample": tc.is_sample,
                    "is_hidden": tc.is_hidden,
                    "order": tc.order,
                    "description": tc.description,
                },
            )
            self._report("TestCase", f"{clone.slug}: {tc.description}", created)

    def _create_all_hints(self, clone, source, ProblemHint):
        """Create all three hint types on a shared-task clone (Tasks 1, 5, 6).

        Source rows for these tasks (Prompt problems) have no hints, so we
        author content from PROMPT_HINT_CONTENT.
        """
        content_by_type = PROMPT_HINT_CONTENT[source.slug]
        for hint_type, content in content_by_type.items():
            _, created = ProblemHint.objects.get_or_create(
                problem=clone,
                hint_type=hint_type,
                defaults={
                    "is_enabled": True,
                    "min_attempts": 2,
                    "content": content,
                },
            )
            self._report("ProblemHint", f"{hint_type} for {clone.slug}", created)

    def _create_single_hint(self, clone, source, mechanism: str, ProblemHint):
        """Create exactly one ProblemHint on a per-mechanism clone (Tasks 2-4).

        Copies content verbatim from the matching source hint row, which
        exists in the demo seed for all three EiPL sources.
        """
        hint_type = MECHANISM_TO_HINT_TYPE[mechanism]
        try:
            source_hint = source.hints.get(hint_type=hint_type)
        except ProblemHint.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f"  Source problem '{source.slug}' is missing "
                    f"hint_type='{hint_type}'. Re-run seed_demo_set_data."
                )
            )
            raise

        _, created = ProblemHint.objects.get_or_create(
            problem=clone,
            hint_type=hint_type,
            defaults={
                "is_enabled": True,
                "min_attempts": 2,
                "content": dict(source_hint.content),
            },
        )
        self._report("ProblemHint", f"{hint_type} for {clone.slug}", created)

    def _report(self, model_name: str, identifier: str, created: bool):
        """Print whether an object was created or already existed."""
        if created:
            self.stdout.write(f"  Created {model_name}: {identifier}")
        else:
            self.stdout.write(f"  Skipped {model_name}: {identifier} (already exists)")
