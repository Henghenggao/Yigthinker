from __future__ import annotations
import ast
import asyncio
import builtins
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel
from yigthinker.types import ToolResult
from yigthinker.session import SessionContext

# Default wall-clock timeout (seconds) for a single df_transform exec().
# Override per-session via settings["df_transform"]["timeout"].
_DEFAULT_TIMEOUT_SECONDS = 30.0

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
    """getattr replacement that blocks access to private/dunder attributes.

    Blocks any attribute name starting with '_' (both single underscore
    and dunder). User transform code has no legitimate need for private
    attributes; single-underscore names like `_metadata` and `_constructor`
    are pandas internals, not public API.
    """
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
    extra_vars: list[str] = []


class DfTransformTool:
    name = "df_transform"
    description = (
        "Execute Pandas/Polars code against a registered DataFrame. "
        "Code runs in a sandboxed namespace — no file I/O, no network, "
        "no imports beyond pandas/numpy/polars. "
        "The input DataFrame is bound to both 'df' and its input_var name. "
        "Use extra_vars=[...] to inject additional registered DataFrames under "
        "their own names for multi-DataFrame merges/joins. "
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
        namespace: dict = {
            "__builtins__": sandbox_builtins,
            "df": df,
            **_ALLOWED_IMPORT_MAP,
        }
        # Also expose the input DataFrame under its own name so code can use
        # natural variable names when joining/merging with extra_vars.
        if input.input_var and input.input_var not in namespace:
            namespace[input.input_var] = df

        # Inject extra variables into the namespace under their registered names.
        for var_name in input.extra_vars:
            if var_name == input.input_var:
                continue
            try:
                namespace[var_name] = ctx.vars.get(var_name)
            except KeyError as exc:
                return ToolResult(tool_use_id="", content=str(exc), is_error=True)

        # Resolve timeout from settings with a 30s default. Users can tune via
        # settings["df_transform"]["timeout"] (seconds, float).
        timeout_setting = ctx.settings.get("df_transform", {}).get(
            "timeout", _DEFAULT_TIMEOUT_SECONDS
        )
        try:
            timeout = float(timeout_setting)
        except (TypeError, ValueError):
            timeout = _DEFAULT_TIMEOUT_SECONDS

        # NOTE on thread leaks: asyncio.wait_for cancels the awaiting coroutine
        # but cannot interrupt CPython bytecode running in a thread. An abusive
        # `while True: pass` will keep spinning in its executor thread even
        # after this function returns an error. We use a per-call
        # ThreadPoolExecutor(max_workers=1) so each timeout leaks at most one
        # thread; the default loop executor is not poisoned. The only complete
        # fix would be subprocess isolation.
        loop = asyncio.get_running_loop()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="df_transform")
        try:
            future = loop.run_in_executor(executor, exec, input.code, namespace)  # noqa: S102
            try:
                await asyncio.wait_for(future, timeout=timeout)
            except asyncio.TimeoutError:
                return ToolResult(
                    tool_use_id="",
                    content=f"Code timed out after {timeout:g} seconds.",
                    is_error=True,
                )
            except ImportError as exc:
                return ToolResult(tool_use_id="", content=str(exc), is_error=True)
            except Exception as exc:
                return ToolResult(
                    tool_use_id="", content=f"Code error: {exc}", is_error=True
                )
        finally:
            # wait=False: do not block on any still-running (abusive) thread.
            # The thread will die when its code returns; the executor object
            # itself is eligible for GC once it finishes.
            executor.shutdown(wait=False)

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
