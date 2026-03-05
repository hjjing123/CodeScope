// Generic Freemarker XSS:
// source argument -> method with Freemarker evidence -> model write sink.
MATCH (sourceNode)-[:ARG]->(m:Method)
WHERE
  any(l IN labels(sourceNode) WHERE l IN [
    'DubboServiceArg', 'JsfXhtmlArg', 'JaxwsArg', 'StrutsActionArg', 'ThriftHandlerArg',
    'NettyHandlerArg', 'JfinalControllerArg', 'JbootControllerArg', 'SpringControllerArg',
    'SolonControllerArg', 'SpringInterceptorArg', 'JspServiceArg', 'WebServletArg',
    'WebXmlServletArg', 'WebXmlFilterArg', 'JaxrsArg', 'HttpHandlerArg'
  ])
  AND NOT coalesce(sourceNode.type, '') IN ['Long', 'Integer', 'HttpServletResponse', 'int', 'long']
  AND exists {
    MATCH (m)-[:HAS_CALL]->(fc:Call)
    WHERE
      (fc.methodFullName IS NOT NULL AND toLower(fc.methodFullName) CONTAINS 'freemarker') OR
      any(t IN coalesce(fc.receiverTypes, []) WHERE toLower(t) CONTAINS 'freemarker') OR
      any(r IN coalesce(fc.receivers, []) WHERE toLower(r) CONTAINS 'freemarker') OR
      'putTemplate' IN coalesce(fc.selectors, [])
  }

MATCH (m)-[:HAS_CALL]->(sinkNode:Call)
WHERE
  ('addAttribute' IN coalesce(sinkNode.selectors, []) AND 'Model' IN coalesce(sinkNode.receiverTypes, [])) OR
  ('put' IN coalesce(sinkNode.selectors, []) AND 'ModelMap' IN coalesce(sinkNode.receiverTypes, [])) OR
  ('addObject' IN coalesce(sinkNode.selectors, []) AND 'ModelAndView' IN coalesce(sinkNode.receiverTypes, []))

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
