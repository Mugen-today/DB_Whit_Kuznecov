"""Reserved backend module. Business operations are not implemented in Storage phase."""


def execute(*args, **kwargs):
    raise NotImplementedError("sync is outside the current Storage scope")
