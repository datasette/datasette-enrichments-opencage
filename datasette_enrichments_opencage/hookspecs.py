from pluggy import HookspecMarker

hookspec = HookspecMarker("datasette")


@hookspec
def register_budget_check(datasette):
    "TODO"