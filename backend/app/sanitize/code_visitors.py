"""AST visitors for Python code sanitization.

Extracted from sanitize_python_code to reduce nesting depth and file size.
"""

import ast


def _get_code_safety():
    """Lazy import of shared.code_safety — only resolvable at runtime."""
    from shared.code_safety import (
        _KEY_LIKE_NAMES,
        DANGEROUS_ATTRS,
        DANGEROUS_BUILTINS,
        DANGEROUS_DUNDER_ATTRS,
        DANGEROUS_MODULES,
        RESTRICTED_MODULES,
        SAFE_OS_OPS,
        is_high_entropy,
        scan_for_secrets,
        scan_for_secrets_regex,
    )

    return {
        "_KEY_LIKE_NAMES": _KEY_LIKE_NAMES,
        "DANGEROUS_ATTRS": DANGEROUS_ATTRS,
        "DANGEROUS_BUILTINS": DANGEROUS_BUILTINS,
        "DANGEROUS_DUNDER_ATTRS": DANGEROUS_DUNDER_ATTRS,
        "DANGEROUS_MODULES": DANGEROUS_MODULES,
        "RESTRICTED_MODULES": RESTRICTED_MODULES,
        "SAFE_OS_OPS": SAFE_OS_OPS,
        "is_high_entropy": is_high_entropy,
        "scan_for_secrets": scan_for_secrets,
        "scan_for_secrets_regex": scan_for_secrets_regex,
    }


class DangerousCodeVisitor(ast.NodeVisitor):
    """Walk the AST and flag dangerous patterns regardless of aliasing."""

    def __init__(self):
        self.warnings: list[str] = []
        # Track aliased names: {local_name: original_module}
        self._aliases: dict[str, str] = {}
        self._cs = _get_code_safety()

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            module_name = alias.name.split(".")[0]
            if module_name in self._cs["DANGEROUS_MODULES"]:
                local_name = alias.asname or alias.name
                self._aliases[local_name] = module_name
                self.warnings.append(f"Dangerous import: {alias.name}")
            elif module_name in self._cs["RESTRICTED_MODULES"]:
                local_name = alias.asname or alias.name
                self._aliases[local_name] = module_name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            module_name = node.module.split(".")[0]
            if module_name in self._cs["DANGEROUS_MODULES"]:
                self.warnings.append(f"Dangerous import from: {node.module}")
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    self._aliases[local_name] = module_name
            elif module_name in self._cs["RESTRICTED_MODULES"]:
                for alias in node.names:
                    imported_name = alias.name
                    if module_name == "os" and imported_name not in self._cs["SAFE_OS_OPS"]:
                        local_name = alias.asname or imported_name
                        self._aliases[local_name] = module_name
                        self.warnings.append(f"Dangerous import from os: {imported_name}")
                    elif module_name == "os":
                        local_name = alias.asname or imported_name
                        self._aliases[local_name] = module_name
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        """Track variable assignments from restricted/dangerous modules.

        Without this, `x = os; x.system("whoami")` bypasses all checks
        because the visitor never learns that `x` is an alias for `os`.
        """
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target_name = node.targets[0].id
            if isinstance(node.value, ast.Name):
                source_name = node.value.id
                if source_name in self._aliases:
                    self._aliases[target_name] = self._aliases[source_name]
                elif source_name in self._cs["DANGEROUS_MODULES"] or source_name in self._cs["RESTRICTED_MODULES"]:
                    self._aliases[target_name] = source_name
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in self._cs["DANGEROUS_BUILTINS"]:
                self.warnings.append(f"Dangerous call: {func_name}()")
            if func_name in self._aliases:
                alias_module = self._aliases[func_name]
                if alias_module in self._cs["DANGEROUS_MODULES"]:
                    self.warnings.append(f"Dangerous call via alias: {func_name} (aliased from {alias_module})")

        if isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if isinstance(node.func.value, ast.Name):
                obj_name = node.func.value.id

                if obj_name in self._cs["DANGEROUS_MODULES"] or obj_name in self._aliases:
                    resolved_module = self._aliases.get(obj_name, obj_name)
                    if resolved_module in self._cs["DANGEROUS_MODULES"]:
                        self.warnings.append(f"Dangerous call: {obj_name}.{attr_name}()")
                    elif resolved_module == "os":
                        if attr_name not in self._cs["SAFE_OS_OPS"]:
                            self.warnings.append(f"Restricted os call: os.{attr_name}() is not allowed")
                    elif resolved_module == "importlib":
                        self.warnings.append(f"Restricted importlib call: {obj_name}.{attr_name}() is not allowed")

            if attr_name in self._cs["DANGEROUS_ATTRS"]:
                if isinstance(node.func.value, ast.Name):
                    obj_name = node.func.value.id
                    resolved = self._aliases.get(obj_name, obj_name)
                    if resolved in self._cs["DANGEROUS_MODULES"] or resolved == "os":
                        self.warnings.append(f"Dangerous call: {obj_name}.{attr_name}()")

            if isinstance(node.func.value, ast.Name):
                if node.func.value.id == "importlib" and attr_name == "import_module":
                    self.warnings.append("Dangerous call: importlib.import_module()")

        if isinstance(node.func, ast.Name) and node.func.id == "getattr":
            if len(node.args) >= 2:
                first_arg = node.args[0]
                if isinstance(first_arg, ast.Name):
                    resolved = self._aliases.get(first_arg.id, first_arg.id)
                    if resolved in self._cs["DANGEROUS_MODULES"] or resolved in self._cs["RESTRICTED_MODULES"]:
                        self.warnings.append(f"Dangerous getattr() on module: {first_arg.id}")

        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript):
        if isinstance(node.value, ast.Name):
            if node.value.id in self._cs["DANGEROUS_BUILTINS"]:
                self.warnings.append(f"Dangerous subscript access on: {node.value.id}()")
        if isinstance(node.value, ast.Attribute):
            if node.value.attr in self._cs["DANGEROUS_DUNDER_ATTRS"]:
                self.warnings.append(f"Dangerous subscript on: {node.value.attr}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if node.attr in self._cs["DANGEROUS_DUNDER_ATTRS"]:
            self.warnings.append(f"Dangerous attribute access: {node.attr}")
        if node.attr == "__init__":
            if isinstance(node.value, ast.Attribute) and node.value.attr in self._cs["DANGEROUS_DUNDER_ATTRS"]:
                self.warnings.append(f"Dangerous chained attribute access: .{node.value.attr}.__init__")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if node.id == "__builtins__":
            self.warnings.append("Dangerous name reference: __builtins__")
        self.generic_visit(node)


class SecretPatternVisitor(ast.NodeVisitor):
    """AST visitor that detects hardcoded secrets in tool source code.

    Two signals:
    1. Regex: string literals matching known secret formats (AWS keys, GitHub
       tokens, etc.) via SECRET_PATTERNS from shared/code_safety.py.
    2. Entropy: assignments to key-like variable names (api_key, token, secret,
       etc.) where the value is a high-entropy string (>=4.5 bits/char, 20+ chars).

    Warnings block tool creation. The fix is always: use os.getenv('CREDENTIAL_X').
    """

    def __init__(self):
        self.warnings: list[str] = []
        self._cs = _get_code_safety()

    def visit_Assign(self, node: ast.Assign):
        """Check assignments for key-like names with high-entropy values."""
        if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
            self.generic_visit(node)
            return

        value = node.value.value
        for target in node.targets:
            if isinstance(target, ast.Name):
                name = target.id
                if self._cs["_KEY_LIKE_NAMES"].search(name) and self._cs["is_high_entropy"](value):
                    self.warnings.append(
                        f"Potential secret in variable '{name}': high-entropy value. "
                        f"Use os.getenv('CREDENTIAL_<KEY>') instead."
                    )
                labels = self._cs["scan_for_secrets_regex"](value)
                for label in labels:
                    self.warnings.append(
                        f"Potential {label} in variable '{name}'. Use os.getenv('CREDENTIAL_<KEY>') instead."
                    )
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr):
        """Check standalone string expressions (docstrings, etc.) for secrets."""
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            labels = self._cs["scan_for_secrets"](node.value.value)
            for label in labels:
                self.warnings.append(f"Potential {label} in string literal.")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        """Check function call arguments for secrets."""
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                labels = self._cs["scan_for_secrets"](arg.value)
                for label in labels:
                    self.warnings.append(f"Potential {label} in function call argument.")
        for kw in node.keywords:
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                labels = self._cs["scan_for_secrets"](kw.value.value)
                for label in labels:
                    self.warnings.append(f"Potential {label} in keyword argument.")
        self.generic_visit(node)
