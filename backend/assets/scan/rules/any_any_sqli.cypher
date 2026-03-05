MATCH (src)
WHERE 'SpringControllerArg' IN coalesce(src.segLabels, [])
MATCH (sink)
WHERE 'SinkSql' IN coalesce(sink.segLabels, [])
MATCH p = shortestPath((src)-[:CALLS|ARG|REF*1..30]->(sink))
RETURN p AS path
LIMIT 200;
