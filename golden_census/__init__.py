"""A characterization harness: run a subject over a manifest of surfaces,
record the normalized bytes, compare a later subject against them.

Nothing here imports the subject. The manifest says what to run, the census
says what the environment around every run is pinned to, folded away or merely
stated, and both are files the consumer owns.
"""

import os
import sys

__version__ = "1.0.0"

#: The interpreter option (`python3 -X golden_census_say_where …`) that makes
#: the package say, on standard error and before anything else, which copy of
#: it was imported. Only the self-check's own children are started with it
#: (`proof._package_argv`), so no run a user makes carries it, and an option
#: and not a variable so it reaches no grandchild: a subject a child starts
#: inherits no `-X`. It lives HERE, above everything the package imports,
#: because this is the first line of the package that runs.
SAY_WHERE_OPTION = "golden_census_say_where"

#: The line it says, before the directory. `proof._heard` splits a child's
#: standard error at this line: everything before it is the interpreter's own
#: startup, everything after is the package's.
SAID_WHERE = "golden-census package directory: "

if SAY_WHERE_OPTION in sys._xoptions:      # see SAY_WHERE_OPTION above
    try:
        sys.stderr.write(
            SAID_WHERE + os.path.dirname(os.path.abspath(__file__)) + "\n")
    except (AttributeError, OSError, ValueError):
        # A closed or absent standard error (`sys.stderr` is None when fd 2
        # is closed): the child then prints no line, and the arm that asked
        # for one says so.
        pass
