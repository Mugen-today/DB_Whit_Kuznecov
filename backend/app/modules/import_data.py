"""Reserved backend module. Business operations are not implemented in Storage phase."""


def execute(*args, **kwargs):
    raise NotImplementedError("import_data is outside the current Storage scope")
