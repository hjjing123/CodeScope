from app.services.scan_external.neo4j_runner import (
    _serialize_graph_value,
    split_cypher_statements,
)
from app.services.scan_external.path_result_postprocess import (
    PathPostprocessConfig,
    postprocess_result_records,
)


def test_split_cypher_statements_ignores_comments() -> None:
    text = """
    // this is line comment;
    MATCH (n) RETURN n;
    /* block comment ; */
    MATCH (m) WHERE m.name = 'x;y' RETURN m;
    """

    statements = split_cypher_statements(text)
    assert len(statements) == 2
    assert statements[0].startswith("MATCH (n)")
    assert "x;y" in statements[1]


def test_split_cypher_statements_skips_empty_segments() -> None:
    text = " ; ; MATCH (n) RETURN count(n); ; "
    statements = split_cypher_statements(text)
    assert statements == ["MATCH (n) RETURN count(n)"]


class _FakeNode:
    def __init__(self, labels, props, element_id):
        self.labels = labels
        self._props = props
        self.element_id = element_id

    def items(self):
        return self._props.items()

    def get(self, key, default=None):
        return self._props.get(key, default)


class _FakeRelationship:
    def __init__(self, rel_type, props, element_id):
        self.type = rel_type
        self._props = props
        self.element_id = element_id

    def items(self):
        return self._props.items()

    def get(self, key, default=None):
        return self._props.get(key, default)


class _FakePath:
    def __init__(self, nodes, relationships):
        self.nodes = nodes
        self.relationships = relationships


def test_serialize_graph_value_preserves_path_edges() -> None:
    path = _FakePath(
        nodes=[
            _FakeNode(["Var"], {"id": "source-1", "name": "filepath"}, "node-1"),
            _FakeNode(["Var"], {"id": "sink-1", "name": "cmdList"}, "node-2"),
        ],
        relationships=[
            _FakeRelationship("ARG", {"argIndex": 0}, "edge-1"),
        ],
    )

    payload = _serialize_graph_value(path)

    assert payload["kind"] == "path"
    assert payload["length"] == 1
    assert payload["nodes"][0]["node_ref"] == "source-1"
    assert payload["edges"][0]["type"] == "ARG"
    assert payload["edges"][0]["from_node_ref"] == "source-1"
    assert payload["edges"][0]["to_node_ref"] == "sink-1"


def test_postprocess_result_records_dedupes_structurally_identical_rows() -> None:
    path_a = _FakePath(
        nodes=[
            _FakeNode(
                ["Var"],
                {"name": "cmd", "file": "/tmp/source/src/A.java", "line": 10},
                "node-a1",
            ),
            _FakeNode(
                ["Call"],
                {"name": "exec", "file": "/tmp/source/src/A.java", "line": 20},
                "node-a2",
            ),
        ],
        relationships=[
            _FakeRelationship("ARG", {"argPosition": 0}, "edge-a1"),
        ],
    )
    path_b = _FakePath(
        nodes=[
            _FakeNode(
                ["Var"],
                {"name": "cmd", "file": "/other/source/src/A.java", "line": 10},
                "node-b1",
            ),
            _FakeNode(
                ["Call"],
                {"name": "exec", "file": "/other/source/src/A.java", "line": 20},
                "node-b2",
            ),
        ],
        relationships=[
            _FakeRelationship("ARG", {"argPosition": 0}, "edge-b1"),
        ],
    )

    records, stats = postprocess_result_records(
        [{"path": path_a}, {"path": path_b}],
        ["path"],
        PathPostprocessConfig(),
    )

    assert len(records) == 1
    assert stats.kept_rows == 1
    assert stats.dropped_duplicate_rows == 1
