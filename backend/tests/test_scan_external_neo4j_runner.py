from app.services.scan_external.neo4j_runner import split_cypher_statements


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
