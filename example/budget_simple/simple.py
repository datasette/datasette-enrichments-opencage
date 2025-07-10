from datasette import hookimpl

n = 1

@hookimpl
def register_budget_check(datasette):
    global n
    if n > 5:
        return False
    n += 1
    return True