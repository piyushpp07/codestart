from pathlib import Path

from claude_code.code_graph import build_code_graph


def test_build_code_graph_resolves_local_python_and_javascript_imports(tmp_path: Path) -> None:
    package = tmp_path / "app"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "helpers.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "main.py").write_text("from app import helpers\n", encoding="utf-8")
    (tmp_path / "widget.js").write_text("import value from './value.js';\n", encoding="utf-8")
    (tmp_path / "value.js").write_text("export default 1;\n", encoding="utf-8")

    graph = build_code_graph(str(tmp_path))

    node_ids = {node["id"] for node in graph["nodes"]}
    edges = {(edge["source"], edge["target"]) for edge in graph["edges"]}
    assert {"app/main.py", "app/helpers.py", "widget.js", "value.js"} <= node_ids
    assert ("app/main.py", "app/helpers.py") in edges
    assert ("widget.js", "value.js") in edges
