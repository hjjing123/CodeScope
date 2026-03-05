// Spring MVC template XSS (view model propagation).
// Keep non-REST controllers and require REF evidence from source argument to sink call.
MATCH (sourceNode:SpringControllerArg)-[:ARG]->(m:Method)
WHERE
  NOT coalesce(sourceNode.type, '') IN ['Long', 'Integer', 'int', 'long']
  AND NOT any(a IN coalesce(sourceNode.classAnnotations, []) WHERE
    a = 'RestController' OR toLower(a) ENDS WITH '.restcontroller'
  )
  AND NOT any(a IN coalesce(sourceNode.methodAnnotations, []) WHERE
    a = 'ResponseBody' OR toLower(a) ENDS WITH '.responsebody'
  )

MATCH (m)-[:HAS_CALL]->(sinkNode:Call)
WHERE
  (
    'addAttribute' IN coalesce(sinkNode.selectors, []) AND
    'Model' IN coalesce(sinkNode.receiverTypes, [])
  ) OR (
    'put' IN coalesce(sinkNode.selectors, []) AND
    'ModelMap' IN coalesce(sinkNode.receiverTypes, [])
  ) OR (
    'addObject' IN coalesce(sinkNode.selectors, []) AND
    'ModelAndView' IN coalesce(sinkNode.receiverTypes, [])
  )

MATCH p = (sourceNode)-[:ARG]->(m)-[:HAS_CALL]->(sinkNode)
WHERE
  none(n IN nodes(p) WHERE coalesce(n.type, '') IN ['Long', 'Integer', 'int', 'long'])
  // Enforce argument-level data participation, not only method co-location.
  AND exists {
    MATCH (argNode)-[argRel:ARG]->(sinkNode)
    WHERE
      coalesce(argRel.argIndex, -1) > 0
      AND NOT 'Lit' IN labels(argNode)
      AND 'Reference' IN labels(argNode)
      AND (sourceNode)-[:REF*1..4]->(argNode)
  }
RETURN p AS path
