from __future__ import annotations
import ast
import builtins
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext

_SAFE_BUILTINS = {
    name: getattr(builtins, name)
    for name in (
        "None", "True", "False", "abs", "all", "any", "bool", "dict",
        "enumerate", "filter", "float", "format", "frozenset", "int",
        "isinstance", "issubclass", "iter", "len", "list", "map", "max",
        "min", "next", "print", "range", "reversed", "round", "set",
        "slice", "sorted", "str", "sum", "tuple", "zip",
    )
}


def _safe_getattr(obj: object, name: str, *default: object) -> object:
    """getattr replacement that blocks access to private/dunder attributes."""
    if isinstance(name, str) and name.startswith("_"):
        raise AttributeError(
            f"Access to private attribute '{name}' is blocked in df_transform sandbox."
        )
    return getattr(obj, name, *default)


_SAFE_BUILTINS["getattr"] = _safe_getattr

_ALLOWED_IMPORT_MAP = {
    "pandas": __import__("pandas"),
    "pd": __import__("pandas"),
    "numpy": __import__("numpy"),
    "np": __import__("numpy"),
}

try:
    import polars as _polars
    _ALLOWED_IMPORT_MAP["polars"] = _polars
    _ALLOWED_IMPORT_MAP["pl"] = _polars
except ImportError:
    pass

# Dunder attributes that can be used to escape the sandbox via object
# introspection (__globals__, __subclasses__, __bases__, etc.).
_BLOCKED_DUNDERS = frozenset({
    "__globals__", "__builtins__", "__subclasses__", "__bases__",
    "__mro__", "__init__", "__class__", "__dict__", "__module__",
    "__code__", "__func__", "__self__", "__closure__", "__wrapped__",
    "__getattribute__", "__reduce__", "__reduce_ex__", "__new__",
    "__get__", "__set__", "__delete__", "__setattr__", "__delattr__",
})

# Module-level attributes that provide access to dangerous stdlib modules.
# These are reachable via injected library objects (e.g. pd.io.common.os).
_BLOCKED_ATTRS = frozenset({
    "os", "subprocess", "sys", "importlib", "ctypes", "shutil",
    "pathlib", "socket", "http", "urllib", "ftplib", "smtplib",
    "webbrowser", "code", "codeop", "compileall", "runpy",
})

# Reject direct access to file/network I/O helpers on injected dataframe libraries.
# We block attribute access itself so code cannot alias a dangerous helper and call
# it later via another variable.
_BLOCKED_IO_ATTRS = frozenset({
    # pandas / polars / numpy readers
    "read_csv", "read_table", "read_fwf", "read_json", "read_html",
    "read_xml", "read_excel", "read_parquet", "read_feather",
    "read_pickle", "read_orc", "read_spss", "read_sas", "read_stata",
    "read_sql", "read_sql_query", "read_sql_table", "read_clipboard",
    "read_gbq", "read_database", "read_database_uri", "read_ipc",
    "read_ndjson", "scan_csv", "scan_parquet", "scan_ipc",
    # writers / sinks
    "to_csv", "to_json", "to_html", "to_xml", "to_excel", "to_parquet",
    "to_feather", "to_pickle", "to_orc", "to_clipboard", "to_sql",
    "write_csv", "write_json", "write_ndjson", "write_excel",
    "write_parquet", "write_ipc", "write_ipc_stream", "write_avro",
    "sink_csv", "sink_parquet", "sink_ipc",
    # numpy binary/text I/O
    "load", "loadtxt", "genfromtxt", "fromfile", "save", "savez",
    "savez_compressed", "savetxt", "tofile",
    # helper classes that open external resources
    "ExcelFile", "ExcelWriter", "HDFStore",
})


def _get_attr_chain(node: ast.Attribute) -> list[str]:
    """Walk an Attribute node to build the full dotted path as a list."""
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    parts.reverse()
    return parts


class _SandboxChecker(ast.NodeVisitor):
    """Raises SyntaxError if blocked dunders or dangerous module paths are accessed."""

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in _BLOCKED_DUNDERS:
            raise SyntaxError(
                f"Access to '{node.attr}' is not allowed in df_transform sandbox."
            )
        if node.attr in _BLOCKED_IO_ATTRS:
            chain = _get_attr_chain(node)
            dotted = ".".join(chain) if chain else node.attr
            raise SyntaxError(
                f"Access to '{dotted}' is blocked in df_transform sandbox. "
                "File and network I/O helpers are not allowed."
            )
        # Block access to dangerous stdlib modules via attribute chains
        # (e.g. pd.io.common.os, np.distutils.exec_command.subprocess)
        if node.attr in _BLOCKED_ATTRS:
            chain = _get_attr_chain(node)
            raise SyntaxError(
                f"Access to '{'.'.join(chain)}' is blocked in df_transform sandbox. "
                f"Module '{node.attr}' is not allowed."
            )
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and node.value in _BLOCKED_DUNDERS:
            raise SyntaxError(
                f"String literal '{node.value}' matches a blocked dunder attribute."
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if any(alias.name == "*" for alias in node.names):
            raise SyntaxError("Wildcard imports are not allowed in df_transform sandbox.")
        if node.module:
            root = node.module.split(".", 1)[0]
            if root in _ALLOWED_IMPORT_MAP:
                for alias in node.names:
                    if alias.name in _BLOCKED_IO_ATTRS:
                        raise SyntaxError(
                            f"Import of '{alias.name}' from '{node.module}' is blocked "
                            "in df_transform sandbox."
                        )
        self.generic_visit(node)


def _check_ast(code: str) -> None:
    """Parse and walk the AST, rejecting any blocked dunder accesses."""
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise SyntaxError(f"Invalid Python syntax: {exc}") from exc
    _SandboxChecker().visit(tree)


def _safe_import(name: str, *args, **kwargs):
    if name not in _ALLOWED_IMPORT_MAP:
        raise ImportError(f"Import '{name}' not allowed in df_transform sandbox. Allowed: {list(_ALLOWED_IMPORT_MAP)}")
    return _ALLOWED_IMPORT_MAP[name]


class DfTransformInput(BaseModel):
    code: str
    input_var: str = "df1"
    output_var: str = "df_result"


class DfTransformTool:
    name = "df_transform"
    description = (
        "Execute Pandas/Polars code against a registered DataFrame. "
        "Code runs in a sandboxed namespace — no file I/O, no network, "
        "no imports beyond pandas/numpy/polars. "
        "Assign the result to 'result'; it will be stored as output_var."
    )
    input_schema = DfTransformInput

    async def execute(self, input: DfTransformInput, ctx: SessionContext) -> ToolResult:
        try:
            _check_ast(input.code)
        except SyntaxError as exc:
            return ToolResult(tool_use_id="", content=f"Code rejected: {exc}", is_error=True)

        try:
            df = ctx.vars.get(input.input_var)
        except KeyError as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)

        sandbox_builtins = {**_SAFE_BUILTINS, "__import__": _safe_import}
        namespace = {
            "__builtins__": sandbox_builtins,
            "df": df,
            **_ALLOWED_IMPORT_MAP,
        }

        try:
            exec(input.code, namespace)  # noqa: S102
        except ImportError as exc:
            return ToolResult(tool_use_id="", content=str(exc), is_error=True)
        except Exception as exc:
            return ToolResult(tool_use_id="", content=f"Code error: {exc}", is_error=True)

        if "result" not in namespace:
            return ToolResult(
                tool_use_id="",
                content="Code must assign to 'result'. Example: result = df[df['col'] > 0]",
                is_error=True,
            )

        result_df = namespace["result"]
        ctx.vars.set(input.output_var, result_df)

        cm = ctx.context_manager
        return ToolResult(
            tool_use_id="",
            content={
                "stored_as": input.output_var,
                "preview": cm.summarize_dataframe_result(result_df),
            },
        )
